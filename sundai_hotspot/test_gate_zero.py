"""Gate zero (SLAB-049): raw paper-match references, identities, the operator's signed ledger and tags, records built
from them, the manifest-bound bootstrap entry with its atomic launch claim, and the selector. No solves: the
"binaries" are placeholders or a tiny fake that writes synthetic outputs. The operator's Ed25519 key is generated at
run time in each test (no key material in the repository), and the GitHub tag API is an in-memory fake that
implements create-only, atomic refs (never the network).
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from sundai_hotspot import gate0_anchor, gate_zero, provenance, reference_validation, slab049, tap_oracle
from sundai_hotspot.coupling_variant import strip_variant_blocks
from sundai_hotspot.evaluators import EVIDENCE_PREFIX, HotSpot6Oracle, make_oracle
from sundai_hotspot.gate0_anchor import (
    AnchorAbsent, AnchorUnavailable, AuthenticationError, ClaimRefused, ClaimUncertain, RefExists, TagReader,
)
from sundai_hotspot.gate_zero import (
    DEFERRED, GATE, HOTSPOT6_TAG, PINNED_REFERENCES_SHA256, REFERENCES, TOLERANCE_K, TOLERANCE_LABEL, VARIANT_TAG,
    GateZeroRefusal, build_record, call_id, evaluator_identity, references_sha256, require_gate_zero, required_calls,
    tap_selector_c, tap_stdout_selector_c,
)
from sundai_hotspot.reference_validation import CallRefused, validate_call
from sundai_hotspot.tap_oracle import REPO_ROOT, HotSpotOracle, HotSpotOracleError, TapLegalityError

HS6_ROOT = REPO_ROOT / "sundai_hotspot6"
FAKE_BINARIES = {
    "hotspot7_default": b"HotSpot 7 placeholder: microchannel support",
    "material_only": b"HotSpot 7 placeholder: microchannel support; " + VARIANT_TAG,
    "hotspot6": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin) dgssv " + HOTSPOT6_TAG,
    "hotspot6_tap_faithful": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin)",
}
ASCEND, MICRO = "ascend910-tap25d-fig6a-raw", "micro150-tap25d-fig5a-raw"
REQUIRED = [row["call"] for row in required_calls()]
P_ASCEND, R_ASCEND = call_id("primary", "hotspot6", ASCEND, 64), call_id("replay", "hotspot6", ASCEND, 64)
P_MICRO, R_MICRO = call_id("primary", "hotspot6", MICRO, 64), call_id("replay", "hotspot6", MICRO, 64)
G32_ASCEND = call_id("primary", "hotspot6", ASCEND, 32)
GOOD = {P_ASCEND: 75.09, R_ASCEND: 75.09, P_MICRO: 116.27, R_MICRO: 116.27}
GRANT_ID = "g49-test"
WINDOW = ("2026-10-31T00:00:00+00:00", "2026-11-01T12:00:00+00:00")
IN_WINDOW = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
NO_LIBRARIES = {"dynamic": False, "libraries": [], "note": "synthetic"}
EMPTY_TREE = hashlib.sha1(b"tree 0\0").hexdigest()  # git's empty tree object, computed here
OPERATOR_ENVIRONMENT = ("SLAB049_LEDGER_ROOT", "SLAB049_OPERATOR_KEY", "SLAB049_ANCHOR_TOKEN", "GH_TOKEN",
                        "CI_ALLOCATION")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_outputs(run: Path, peak_c: float, drop_k: float = 1.0, *, grid: int = 64, layers: int = 8,
                  headered: bool = True, omit_block: str | None = None) -> None:
    """Synthetic outputs with the shape HotSpot writes: one steady line per unit of every LCF layer (also on stdout,
    as HotSpot 6.0 prints it) plus package nodes, and a grid file of `layers` sections of grid x grid cells.
    The defaults are the evaluator's real shape (64 x 64, 8 headered layers); other values make shape controls."""
    kelvin = peak_c + 273.15
    lines = []
    for layer in slab049.read_lcf(run / "samplelayers.lcf", run):
        for unit in slab049.read_flp(layer["flp"]):
            name = f"layer_{layer['layer']}_{unit['name']}"
            if name != omit_block:
                lines.append(f"{name}\t{kelvin if name == 'layer_4_Chiplet_0' else kelvin - 20 - layer['layer']:.2f}")
    lines += [f"hsp_TIM\t{kelvin - 30:.2f}", f"hsink_TIM\t{kelvin - 40:.2f}", f"inode_0\t{kelvin - 45:.2f}"]
    (run / "sample.steady").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run / "stdout.txt").write_text("Unit\tSteady(Kelvin)\n" + "\n".join(lines) + "\n", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    hot = (grid // 4) * grid + grid // 4  # one hot cell, inside the grid
    parts = []
    for layer in range(layers):
        if headered:
            parts.append(f"Layer {layer}:\n")
        base = 380.0 - (drop_k if layer == 7 else 0.0) - (0.5 * layer if layer >= 4 else 0.0)
        parts.append("".join(f"{cell}\t{base + (1.0 if cell == hot else 0.0):.2f}\n" for cell in range(grid * grid)))
    (run / "sample.grid.steady").write_text("".join(parts), encoding="utf-8")


class FakeGitHub:
    """GitHub's git-data API as gate0_anchor uses it, in memory (no network). A ref create is atomic and create-only,
    as GitHub's is: a second create of the same ref raises RefExists. Commits are immutable. Failure injection:
    `down` holds (method, path prefix) pairs that fail as an outage would (AnchorUnavailable, before anything
    happens); `fail_create` maps a part of a ref's name to "before" (an outage before its create) or "after" (the
    create happens and its answer is lost); `before_read(path)` runs before a ref is read and `before_create(ref)`
    before a ref create takes the lock (a barrier makes two requests overlap)."""

    def __init__(self):
        self.refs, self.commits, self.log = {}, {}, []
        self.lock = threading.Lock()
        self.down: set[tuple[str, str]] = set()
        self.fail_create: dict[str, str] = {}
        self.before_read = None
        self.before_create = None

    def __call__(self, method: str, path: str, body: dict | None = None):
        with self.lock:
            self.log.append((method, path))
        if any(method == down_method and path.startswith(prefix) for down_method, prefix in self.down):
            raise AnchorUnavailable(f"fake outage: {method} {path}")
        if method == "GET" and path.startswith("/git/ref/"):
            if self.before_read:
                self.before_read(path)
            name = "refs/" + path[len("/git/ref/"):]
            with self.lock:
                sha = self.refs.get(name)
            if sha is None:
                raise AnchorAbsent(path)
            return {"ref": name, "object": {"type": "commit", "sha": sha}}
        if method == "GET" and path.startswith("/git/commits/"):
            with self.lock:
                commit = self.commits.get(path[len("/git/commits/"):])
            if commit is None:
                raise AnchorUnavailable("HTTP 404")  # github_request: only a ref's 404 can be an absence
            return json.loads(json.dumps(commit))
        if method == "POST" and path == "/git/commits":
            commit = {"message": body["message"], "tree": {"sha": body["tree"]},
                      "parents": [{"sha": parent} for parent in body["parents"]]}
            sha = hashlib.sha1(json.dumps(commit, sort_keys=True).encode("utf-8")).hexdigest()
            with self.lock:
                self.commits[sha] = {"sha": sha, **commit}
            return {"sha": sha}
        if method == "POST" and path == "/git/refs":
            mode = next((how for part, how in self.fail_create.items() if part in body["ref"]), None)
            if mode == "before":
                raise AnchorUnavailable(f"fake outage before creating {body['ref']}")
            if self.before_create:
                self.before_create(body["ref"])
            with self.lock:
                if body["ref"] in self.refs:
                    raise RefExists(path)
                self.refs[body["ref"]] = body["sha"]
            if mode == "after":
                raise AnchorUnavailable("the answer to a create that happened was lost")
            return {"ref": body["ref"], "object": {"type": "commit", "sha": body["sha"]}}
        raise AnchorUnavailable(f"the fake has no {method} {path}")

    def ref(self, kind: str, call: str, grant_id: str = GRANT_ID) -> str:
        return "refs/" + gate0_anchor.tag_ref(grant_id, kind, call)

    def has(self, kind: str, call: str) -> bool:
        return self.ref(kind, call) in self.refs

    def drop(self, kind: str, call: str) -> None:
        """Only a test can delete in the create-only namespace."""
        del self.refs[self.ref(kind, call)]

    def launch_tags(self) -> list[str]:
        return sorted(name for name in self.refs if "/launch-" in name)

    def admit_ref(self, seq: int, grant_id: str = GRANT_ID) -> str:
        return "refs/" + gate0_anchor.admit_ref(grant_id, seq)

    def admitted_calls(self) -> list[str]:
        """The admission chain's calls in order, read straight from the fake's refs."""
        calls = []
        for seq in range(1, 100):
            sha = self.refs.get(self.admit_ref(seq))
            if sha is None:
                return calls
            calls.append(json.loads(self.commits[sha]["message"])["call"])
        return calls


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory(prefix="gate-zero-")
        self.root = Path(self._directory.name)
        self.binaries = {}
        for kind, data in FAKE_BINARIES.items():
            path = self.root / f"bin-{kind}"
            path.write_bytes(data)
            self.binaries[kind] = path

    def tearDown(self):
        self._directory.cleanup()


@unittest.skipUnless(os.name == "posix", "the operator's ledger is POSIX (flock, read-only entries); "
                     "validate-reference refuses elsewhere")
class OperatorCase(TempDirCase):
    """The operator's side in miniature: an Ed25519 key generated at run time (never stored in the repository) and
    pinned into a manifest generated for this test, which validate-reference, record and report then read. The
    operator's environment is cleared and the network is unreachable."""

    def setUp(self):
        super().setUp()
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in OPERATOR_ENVIRONMENT:
            os.environ.pop(name, None)
        self.patch(gate0_anchor.urllib.request, "urlopen", mock.Mock(side_effect=AssertionError("network used")))
        self.key = Ed25519PrivateKey.generate()
        self.public = gate0_anchor.public_key_hex(self.key)
        self.key_file = self.root / "operator.pem"
        self.key_file.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption()))
        self.manifest_path = self.root / slab049.MANIFEST_NAME
        self.patch(slab049, "OPERATOR_PUBLIC_KEY", self.public)
        self.patch(slab049, "MANIFEST_PATH", self.manifest_path)
        self.regenerate_manifest()

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def regenerate_manifest(self) -> None:
        self.manifest_path.write_bytes(slab049._dump(slab049.build_call_list()))
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest_sha256 = _sha256(self.manifest_path)
        self.calls = {c["id"]: c for c in self.manifest["calls"]}
        self.envelopes = {name: float(c["accounting"]["reserved_cpu_s"]) for name, c in self.calls.items()}

    def grant(self, label: str = "grant", **kwargs) -> "Scenario":
        return Scenario(self, label, **kwargs)

    def charged(self, scenario: "Scenario") -> float:
        """The grant's anchored charge as the admission computes it, read through this scenario's ledger."""
        ledger = scenario.ledger()
        chain = scenario.tags.admissions(ledger["grant"], self.manifest_sha256, self.envelopes)
        return gate0_anchor.admission_charge(chain, ledger, scenario.tags, scenario.grant_id, self.manifest_sha256)

    def record(self, scenario: "Scenario", binary: Path | None = None, kind: str = "hotspot6") -> dict:
        return build_record(kind, binary or self.binaries["hotspot6"], ledger_root=scenario.root, tags=scenario.tags)

    def require(self, scenario: "Scenario", record, binary: Path | None = None, **kwargs) -> dict:
        return require_gate_zero("hotspot6", binary or self.binaries["hotspot6"], record, ledger_root=scenario.root,
                                 tags=scenario.tags, **kwargs)


class Scenario:
    """One operator ledger root opened with a signed grant (gate0_anchor.open_ledger), the tag API it is read
    through, and the operator's reserve and settle tags. `signer` signs everything; any signer other than the case's
    key is an attacker without the operator's key."""

    def __init__(self, case: OperatorCase, label: str, *, api: FakeGitHub | None = None, calls=None,
                 window=WINDOW, cap: float = 600.0, grant_id: str = GRANT_ID, signer: Ed25519PrivateKey | None = None):
        self.case, self.grant_id, self.key = case, grant_id, signer or case.key
        self.public = gate0_anchor.public_key_hex(self.key)
        self.api = api or FakeGitHub()
        self.tags = TagReader(self.api)
        base = case.root / label
        self.root, self.runs = base / "ledger-root", base / "runs"
        self.grant_entry = gate0_anchor.open_ledger(self.root, self.key, case.manifest_sha256, grant_id=grant_id,
                                                    calls=calls or sorted(case.calls), not_before_utc=window[0],
                                                    not_after_utc=window[1], cpu_cap_s=cap)

    @property
    def dir(self) -> Path:
        return gate0_anchor.ledger_dir(self.root, self.case.manifest_sha256)

    def ledger(self) -> dict:
        return gate0_anchor.read_ledger(self.root, self.public, self.case.manifest_sha256)

    def entries(self, call: str) -> dict:
        return gate0_anchor.call_entries(self.ledger(), call)

    def tag(self, kind: str, call: str, message: str) -> None:
        commit = self.api("POST", "/git/commits", {"message": message, "tree": EMPTY_TREE, "parents": []})
        self.api("POST", "/git/refs", {"ref": self.api.ref(kind, call, self.grant_id), "sha": commit["sha"]})

    def reserve(self, *calls: str) -> None:
        for call in calls:
            self.tag("reserve", call, gate0_anchor.tag_message("reserve", self.grant_id, self.case.manifest_sha256,
                                                               call))

    def settle(self, *calls: str) -> None:
        """The settle tag from the ledger's own settlement: the message validate-reference prints."""
        for call in calls:
            settlement = self.entries(call)["settlement"]
            self.tag("settle", call, gate0_anchor.tag_message(
                "settle", self.grant_id, self.case.manifest_sha256, call, status=settlement["status"],
                receipt_sha256=settlement["receipt_sha256"], outputs=settlement["outputs"],
                charged_cpu_s=settlement["charged_cpu_s"]))

    def admit(self, call: str, out: Path, **kwargs) -> dict:
        """The real admission (gate0_anchor.admit_and_reserve) for one call, as validate-reference makes it."""
        if not self.api.has("reserve", call):
            self.reserve(call)
        return gate0_anchor.admit_and_reserve(
            self.root, self.key, self.public, self.case.manifest_sha256, call,
            {"out": Path(out).resolve().as_posix(), "reserved_cpu_s": self.case.envelopes[call]}, request=self.api,
            envelopes=self.case.envelopes, now=IN_WINDOW, **kwargs)

    def fabricate(self, peaks: dict, *, binary: Path | None = None, settled: dict | None = None,
                  edit: dict | None = None, receipt_signer: Ed25519PrivateKey | None = None,
                  charged_cpu_s: float = 6.0) -> None:
        """Calls exactly as validate-reference and the operator leave them, with synthetic outputs instead of a
        solve: the reserve tag, the admission (its tag and the signed reservation), the run directory and its signed
        receipt, the launch claim, the signed settlement and the settle tag. peaks maps a call id to its peak (C) or
        to write_outputs keyword arguments; settled maps a call id to a (status, exit_status) other than
        ("exited", 0); edit maps a call id to a change made to its receipt before it is signed (a key holder's
        consistent forgery)."""
        identity = evaluator_identity("hotspot6", binary or self.case.binaries["hotspot6"])
        for name, peak in peaks.items():
            call = self.case.calls[name]
            reference = gate_zero.reference(call["reference"])
            run = self.runs / name
            shutil.copytree(REPO_ROOT / reference.inputs, run)
            write_outputs(run, **(peak if isinstance(peak, dict) else {"peak_c": peak}))
            status, exit_status = (settled or {}).get(name, ("exited", 0))
            reservation = self.admit(name, run)
            claim = gate0_anchor.claim_launch(self.api, self.grant_id, self.case.manifest_sha256, name,
                                              reservation_sha256=gate0_anchor.digest(reservation))
            receipt = {"schema": gate_zero.RECEIPT_SCHEMA, "call": name, "role": call["role"],
                       "replay_of": call["replay_of"], "manifest_sha256": self.case.manifest_sha256,
                       "grant_id": self.grant_id, "reservation_sha256": gate0_anchor.digest(reservation),
                       "admission": reservation["admission"], "evaluator": identity, "reference": reference.id, "layout_identity": reference.layout_identity,
                       "raw_layout_sha256": reference.raw_layout_sha256, "grid": call["grid"], "status": status,
                       "exit_status": exit_status, "inputs": gate_zero.frozen_inputs(reference),
                       "runtime": NO_LIBRARIES, "claim": {"ref": claim["ref"], "commit_sha": claim["commit_sha"]},
                       "outputs": {output: _sha256(run / output) for output in gate_zero.RECEIPT_OUTPUTS}}
            if edit and name in edit:
                edit[name](receipt)
            (run / "receipt.json").write_bytes(reference_validation._json(gate0_anchor.sign(receipt_signer or self.key,
                                                                                            receipt)))
            gate0_anchor.append(self.root, self.key, self.public, self.case.manifest_sha256, "settlement", name, {
                "status": status, "exit_status": exit_status, "outputs": receipt["outputs"],
                "receipt_sha256": _sha256(run / "receipt.json"), "charged_cpu_s": charged_cpu_s,
                "reserved_cpu_s": call["accounting"]["reserved_cpu_s"], "out": run.resolve().as_posix()})
            self.settle(name)

    def run_dir(self, call: str) -> Path:
        return Path(self.entries(call)["reservation"]["out"])


class PinnedReferenceTests(unittest.TestCase):
    def test_references_values_roles_and_digest_are_pinned(self):
        self.assertEqual(references_sha256(), PINNED_REFERENCES_SHA256)
        self.assertEqual({r.id: (r.role, r.paper_c, r.layout_identity) for r in REFERENCES}, {
            ASCEND: (GATE, 75.48, "raw"), MICRO: (GATE, 115.94, "raw"),
            "ascend910-tap25d-fig6c": (DEFERRED, 75.47, "tap-solution"),
            "micro150-tap25d-fig5c": (DEFERRED, 94.89, "tap-solution")})
        self.assertEqual((TOLERANCE_K, TOLERANCE_LABEL, gate_zero.GRID, gate_zero.INTERPOSER_MM),
                         (1.0, "prospective computational reference-reproduction tolerance", 64, 45))

    def test_the_predicate_requires_four_native6_grid64_outcomes_and_no_deferred_call(self):
        self.assertEqual(REQUIRED, [P_ASCEND, R_ASCEND, P_MICRO, R_MICRO])
        self.assertEqual(len(set(REQUIRED)), 4)  # a primary and its replay never share an identity
        manifest = slab049.build_call_list()
        self.assertEqual(sorted(c["id"] for c in manifest["calls"] if c["gating"]), sorted(REQUIRED))
        deferred = [r.id for r in REFERENCES if r.role == DEFERRED]
        self.assertFalse([c for c in manifest["calls"] if c["reference"] in deferred])
        self.assertEqual(sorted(manifest["deferred"]), sorted(deferred))
        self.assertTrue(all(d["calls"] == 0 and d["status"] == "pending verification"
                            for d in manifest["deferred"].values()))

    def test_frozen_inputs_are_fresh_45_mm_tap_configs(self):
        for reference in gate_zero.GATE_REFERENCES:
            config = slab049.read_hotspot_config(REPO_ROOT / reference.inputs / "new_hotspot.config")
            self.assertEqual((config["r_convec"], config["s_sink"], config["s_spreader"], config["grid_rows"],
                              config["grid_map_mode"]), ("0.011111111111111112", "0.18", "0.09", "64", "center"))
            for name, digest in gate_zero.frozen_inputs(reference).items():
                self.assertEqual(_sha256(REPO_ROOT / reference.inputs / name), digest)

    def test_a_changed_reference_input_changes_the_pinned_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for reference in gate_zero.GATE_REFERENCES:
                shutil.copytree(REPO_ROOT / reference.inputs, root / reference.inputs)
            self.assertEqual(references_sha256(root), PINNED_REFERENCES_SHA256)
            sums = root / gate_zero.GATE_REFERENCES[0].inputs / "SHA256SUMS"
            sums.write_text(sums.read_text() + "0" * 64 + "  extra.flp\n")
            self.assertNotEqual(references_sha256(root), PINNED_REFERENCES_SHA256)


class RawGeometryTests(unittest.TestCase):
    """root #56858: the paper-match references are SLAB-048's raw geometry, judged by the continuous rules only."""

    def test_raw_layouts_are_slab048s_raw_sections_pinned_by_their_own_content_hash(self):
        for reference in gate_zero.GATE_REFERENCES:
            document = json.loads((REPO_ROOT / reference.raw_vendored).read_text(encoding="utf-8"))
            self.assertEqual(slab049.raw_layout_sha256(document["raw"]), reference.raw_layout_sha256)
            self.assertEqual(document["raw_layout_sha256"], reference.raw_layout_sha256)
            self.assertEqual((document["source"]["pull_request"], document["source"]["commit"],
                              document["source"]["path"], document["source"]["section"]),
                             (57, slab049.SLAB048_COMMIT, reference.raw_record, "raw"))
            self.assertEqual(document["raw"]["label"], "raw reconstruction (approximate, from published figure)")
            record = REPO_ROOT / reference.raw_record
            if record.is_file():  # SLAB-048 (#57) is merged: its own raw section must still carry the pin
                self.assertEqual(slab049.raw_layout_sha256(json.loads(record.read_text(encoding="utf-8"))["raw"]),
                                 reference.raw_layout_sha256)

    def test_annotations_never_count_and_any_raw_change_fails(self):
        """SLAB-048 keeps raw byte-stable and puts its notes in raw_annotations/snapped_annotations: descriptive only."""
        reference = gate_zero.reference(ASCEND)
        vendored = json.loads((REPO_ROOT / reference.raw_vendored).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / reference.raw_vendored).parent.mkdir(parents=True)
            shutil.copy(REPO_ROOT / reference.raw_vendored, root / reference.raw_vendored)
            record = root / reference.raw_record
            record.parent.mkdir(parents=True)

            def write_record(raw, **sections):
                record.write_text(json.dumps({"raw": raw, **sections}), encoding="utf-8")
            annotations = {"raw_annotations": {"identity": {"content_sha256": "0" * 64}, "role": "anything at all",
                                               "centers_mm": [[0.0, 0.0]] * 6},
                           "snapped_annotations": {"rotated": [False] * 6}}
            write_record(vendored["raw"], **annotations)
            self.assertEqual(slab049.load_raw_layout(reference, root)["raw"], vendored["raw"])  # annotations ignored
            for field, change in (("centers_mm", lambda raw: raw["centers_mm"][0].__setitem__(0, 17.1502)),
                                  ("rotated", lambda raw: raw["rotated"].__setitem__(1, True)),
                                  ("label", lambda raw: raw.__setitem__("label", "relabelled"))):
                with self.subTest(raw=field):
                    moved = json.loads(json.dumps(vendored["raw"]))
                    change(moved)
                    write_record(moved, **annotations)
                    with self.assertRaisesRegex(slab049.ReferenceGeometryError, "changed after it was pinned"):
                        slab049.load_raw_layout(reference, root)
            record.unlink()
            edited = json.loads(json.dumps(vendored))
            edited["raw"]["rotated"][1] = True
            (root / reference.raw_vendored).write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(slab049.ReferenceGeometryError, "pinned content hash"):
                slab049.load_raw_layout(reference, root)

    @unittest.skipUnless(hasattr(getattr(tap_oracle, "TapGeometry", None), "continuous_centers_for"),
                         "SLAB-048's TapGeometry (PR #57) is not merged yet; this cross-check runs once both are in")
    def test_slab048s_continuous_rules_accept_the_raw_layouts_that_its_lattice_refuses(self):
        for reference in gate_zero.GATE_REFERENCES:
            geometry = tap_oracle.TapGeometry.load(f"{reference.fixture}-45mm")
            raw = slab049.load_raw_layout(reference)["raw"]
            design = geometry.design_from_centers(raw["centers_mm"], raw["rotated"])
            geometry.continuous_centers_for(design)
            with self.assertRaises(TapLegalityError):
                geometry.centers_for(design)

    def test_raw_centres_are_off_the_lattice_yet_pass_the_continuous_rules(self):
        for reference in gate_zero.GATE_REFERENCES:
            spec = slab049.reference_spec(reference.id)
            self.assertEqual(spec["geometry"], {"rules": slab049.CONTINUOUS_RULES, "search_lattice_checked": False,
                                                "violations": []})
            raw = slab049.load_raw_layout(reference)["raw"]
            self.assertEqual([[x, y] for x, y in zip(spec["x"], spec["y"])], raw["centers_mm"])
            self.assertEqual(spec["rotated"], raw["rotated"])
            self.assertTrue(any(abs(v * 2 - round(v * 2)) > 1e-6 for v in spec["x"] + spec["y"]),
                            f"{reference.id} should sit off the 0.5 mm search lattice")

    def test_the_search_path_still_refuses_the_raw_layouts(self):
        # The oracle hashes its fixture config relative to the repository, so the 45 mm copy lives under it briefly.
        with tempfile.TemporaryDirectory(prefix=".slab049-search-path-", dir=REPO_ROOT) as directory:
            placeholder = Path(directory) / "hotspot"
            placeholder.write_bytes(FAKE_BINARIES["hotspot7_default"])
            for reference in gate_zero.GATE_REFERENCES:
                fixture = reference.fixture
                config = Path(directory) / f"sys_{fixture}_45mm.cfg"
                text = tap_oracle.TAP_CONFIGS[fixture].read_text(encoding="utf-8")
                self.assertEqual(text.count("intp_size = 50"), 1)
                config.write_text(text.replace("intp_size = 50", "intp_size = 45"), encoding="utf-8")
                spec = slab049.reference_spec(reference.id)
                with mock.patch.dict(tap_oracle.TAP_CONFIGS, {fixture: config}):
                    oracle = HotSpotOracle(64, 64, fixture=fixture, hotspot_binary=placeholder)
                with self.assertRaises(TapLegalityError, msg=reference.id) as refused:
                    oracle.centers_for(oracle.design_from_centers(list(zip(spec["x"], spec["y"]))))
                if fixture == "micro150":  # catalog orientation: refused by the lattice itself
                    self.assertIn("placement grid", str(refused.exception))

    def test_each_continuous_rule_rejects_its_own_violation(self):
        footprints, halos = [(10.0, 10.0), (10.0, 10.0)], [0.2, 0.2]
        self.assertEqual(slab049.continuous_violations(footprints, [[10.0, 10.0], [21.0, 10.0]], halos, 45.0), [])
        cases = {"margin": [[5.5, 10.0], [21.0, 10.0]], "overlap with their halos": [[10.0, 10.0], [20.3, 10.0]],
                 "spacing": [[10.0, 10.0], [20.05, 10.05]]}
        for rule, centres in cases.items():
            with self.subTest(rule=rule):
                problems = slab049.continuous_violations(footprints, centres, [0.0, 0.0] if rule == "spacing" else halos,
                                                         45.0)
                self.assertTrue(any(rule in problem for problem in problems), problems)

    def test_a_raw_layout_that_breaks_a_continuous_rule_is_refused(self):
        reference = gate_zero.reference(MICRO)
        document = json.loads(json.dumps(slab049.load_raw_layout(reference)))
        document["raw"]["centers_mm"][1] = list(document["raw"]["centers_mm"][0])
        with self.assertRaisesRegex(slab049.ReferenceGeometryError, "continuous rules"):
            slab049.spec_from_raw_layout(document, reference.fixture)
        document = json.loads(json.dumps(slab049.load_raw_layout(reference)))
        document["raw"]["rotated"][0] = True  # an unrotated catalog footprint flagged as turned
        with self.assertRaisesRegex(slab049.ReferenceGeometryError, "turned as flagged"):
            slab049.spec_from_raw_layout(document, reference.fixture)


class EvaluatorIdentityTests(TempDirCase):
    def test_each_kind_accepts_its_own_binary_and_refuses_the_others(self):
        for kind, path in self.binaries.items():
            self.assertEqual(evaluator_identity(kind, path)["binary_sha256"], _sha256(path))
            for other, other_path in self.binaries.items():
                if other != kind:
                    with self.assertRaises(GateZeroRefusal, msg=f"{kind} accepted a {other} binary"):
                        evaluator_identity(kind, other_path)

    def test_missing_binary_and_unknown_kind_are_refused(self):
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot6", self.root / "absent")
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot8", self.binaries["hotspot6"])

    @unittest.skipUnless((HS6_ROOT / "hotspot").is_file() and (HS6_ROOT / "hotspot-tap-faithful").is_file(),
                         "both HotSpot 6.0 binaries are built in the image")
    def test_built_hotspot6_binaries_identify_correctly_and_carry_their_provenance(self):
        for kind, name in (("hotspot6", "hotspot"), ("hotspot6_tap_faithful", "hotspot-tap-faithful")):
            identity = evaluator_identity(kind, HS6_ROOT / name)
            record = provenance.require_build_provenance(kind, HS6_ROOT / name, identity["binary_sha256"])["provenance"]
            self.assertEqual(record["architecture"], platform.machine())
            self.assertTrue(record["debug_info"])  # HotSpot 6.0's CFLAGS always add -g
            self.assertTrue(any("-g" in line for line in record["makefile_flag_lines"]))
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot6", HS6_ROOT / "hotspot-tap-faithful")
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot7_default", HS6_ROOT / "hotspot")

    def test_temperature_labels_never_call_a_simulation_measured(self):
        for kind, label in gate_zero.TEMPERATURE_LABELS.items():
            self.assertTrue(label.startswith("simulated ("), kind)
            self.assertNotIn("measured", label)
        self.assertIn("withdrawn pending the HS6 correction", gate_zero.TEMPERATURE_LABELS["hotspot7_default"])


class SelectorTests(unittest.TestCase):
    def test_steady_selector_is_the_maximum_block(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            shutil.copytree(REPO_ROOT / gate_zero.GATE_REFERENCES[0].inputs, run)
            write_outputs(run, 75.48)
            value, block = tap_selector_c(run / "sample.steady")
            self.assertAlmostEqual(value, 75.48, places=9)
            self.assertEqual(block, "layer_4_Chiplet_0")

    def test_stdout_selector_reads_hotspot6_output_and_not_hotspot7_output(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = Path(directory) / "stdout.txt"
            stdout.write_text("Unit\tSteady(Kelvin)\nlayer_4_Chiplet_0\t348.63\ninode_0\t320.00\n", encoding="utf-8")
            self.assertAlmostEqual(tap_stdout_selector_c(stdout), 75.48, places=9)
            stdout.write_text("Parsing input files...\nCreating thermal circuit...\nSimulation complete.\n")
            with self.assertRaises(ValueError):
                tap_stdout_selector_c(stdout)

    def test_steady_reader_rejects_duplicates_and_garbage(self):
        with tempfile.TemporaryDirectory() as directory:
            steady = Path(directory) / "sample.steady"
            for text in ("a\t330.00\na\t331.00\n", "a\tnan\n", "a\tinf\n", "a\t-1.00\n", "a\t5000.00\n", "\n"):
                steady.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError, msg=text):
                    gate_zero.read_steady_values(steady)


class OperatorLedgerTests(OperatorCase):
    """gate0_anchor's signed ledger (warden #56967 P2-1, P2-2; astra #57024): only the operator's key writes it, the
    entries form one chain, the grant binds the ledger's own place, and each call is reserved and settled once."""

    def test_entries_are_signed_chained_and_bound_to_their_place(self):
        scenario = self.grant()
        scenario.fabricate({P_ASCEND: 75.09})
        ledger = scenario.ledger()
        self.assertEqual([entry["kind"] for entry in ledger["entries"]], ["grant", "reservation", "settlement"])
        for previous, entry in zip(ledger["entries"], ledger["entries"][1:]):
            self.assertEqual(entry["prev_sha256"], gate0_anchor.digest(previous))
        self.assertEqual(ledger["dir"], (self.root / "grant" / "ledger-root").resolve() / f"slab049-{self.manifest_sha256}")
        grant = ledger["grant"]
        self.assertEqual((grant["grant_id"], grant["manifest_sha256"], grant["cpu_cap_s"], grant["not_before_utc"],
                          grant["not_after_utc"], grant["ledger_dir"]),
                         (GRANT_ID, self.manifest_sha256, 600.0, WINDOW[0], WINDOW[1], ledger["dir"].as_posix()))
        self.assertEqual(grant["calls"], sorted(self.calls))

    def test_edited_unsigned_foreign_gapped_or_missing_entries_never_verify(self):
        attacker = Ed25519PrivateKey.generate()

        def rewrite(scenario, seq, change):
            path = scenario.dir / f"{seq:06d}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            change(data)
            path.chmod(0o644)
            path.write_text(json.dumps(data), encoding="utf-8")

        def resign(data):
            data.update(gate0_anchor.sign(attacker, {k: v for k, v in data.items() if k != "signature"}))
        cases = {
            "an edited field": lambda s: rewrite(s, 1, lambda d: d.update(reserved_cpu_s=1.0)),
            "a stripped signature": lambda s: rewrite(s, 2, lambda d: d.pop("signature")),
            "an attacker's signature": lambda s: rewrite(s, 2, resign),
            "a deleted middle entry": lambda s: (s.dir / "000001.json").unlink(),
            "a deleted grant": lambda s: (s.dir / "000000.json").unlink(),
            "an emptied entry": lambda s: rewrite(s, 2, lambda d: d.clear()),
            "an unreadable entry": lambda s: ((s.dir / "000002.json").chmod(0o644)
                                              or (s.dir / "000002.json").write_text("{", encoding="utf-8")),
            "a deleted ledger": lambda s: shutil.rmtree(s.root),
        }
        for label, change in cases.items():
            with self.subTest(case=label):
                scenario = self.grant(label.replace(" ", "-").replace("'", ""))
                scenario.fabricate({P_ASCEND: 75.09})
                change(scenario)
                with self.assertRaises(AuthenticationError):
                    scenario.ledger()
        forged = self.grant("forged", signer=attacker)  # a whole ledger written without the operator's key
        with self.assertRaisesRegex(AuthenticationError, "does not verify"):
            gate0_anchor.read_ledger(forged.root, self.public, self.manifest_sha256)
        first, second = self.grant("splice-a"), self.grant("splice-b")  # both signed by the operator's own key
        first.fabricate({P_ASCEND: 75.09})
        second.fabricate({P_ASCEND: 75.09})
        target = second.dir / "000002.json"
        target.chmod(0o644)
        shutil.copy(first.dir / "000002.json", target)  # a valid entry, from another ledger's chain
        with self.assertRaisesRegex(AuthenticationError, "breaks the chain"):
            second.ledger()

    def test_a_ledger_copied_elsewhere_or_a_replayed_grant_is_refused(self):
        scenario = self.grant()
        scenario.fabricate({P_ASCEND: 75.09})
        elsewhere = self.root / "elsewhere"
        shutil.copytree(scenario.root, elsewhere)
        with self.assertRaisesRegex(AuthenticationError, "another ledger directory"):
            gate0_anchor.read_ledger(elsewhere, self.public, self.manifest_sha256)
        replayed = gate0_anchor.ledger_dir(self.root / "replayed", self.manifest_sha256)
        replayed.mkdir(parents=True)
        shutil.copy(scenario.dir / "000000.json", replayed / "000000.json")
        with self.assertRaisesRegex(AuthenticationError, "another ledger directory"):
            gate0_anchor.read_ledger(self.root / "replayed", self.public, self.manifest_sha256)
        other = hashlib.sha256(b"another manifest").hexdigest()
        target = gate0_anchor.ledger_dir(self.root / "other-manifest", other)
        target.mkdir(parents=True)
        shutil.copy(scenario.dir / "000000.json", target / "000000.json")
        with self.assertRaises(AuthenticationError):
            gate0_anchor.read_ledger(self.root / "other-manifest", self.public, other)
        with self.assertRaises(AuthenticationError):
            gate0_anchor.ledger_dir(self.root, "../not-a-manifest-id")
        with self.assertRaises(FileExistsError):  # one grant per ledger
            gate0_anchor.open_ledger(scenario.root, self.key, self.manifest_sha256, grant_id="again", calls=[P_ASCEND],
                                     not_before_utc=WINDOW[0], not_after_utc=WINDOW[1], cpu_cap_s=1.0)

    def test_each_call_is_admitted_once_and_settled_once_inside_the_grant(self):
        scenario = self.grant(calls=[P_ASCEND, R_ASCEND])
        out = self.root / "out"

        def settle(call, key=self.key):
            return gate0_anchor.append(scenario.root, key, self.public, self.manifest_sha256, "settlement", call, {})
        with self.assertRaisesRegex(AuthenticationError, "no open reservation"):
            settle(P_ASCEND)
        scenario.admit(P_ASCEND, out)
        with self.assertRaisesRegex(gate0_anchor.AdmissionRefused, "admitted once"):
            scenario.admit(P_ASCEND, out)
        settle(P_ASCEND)
        with self.assertRaises(AuthenticationError):
            settle(P_ASCEND)
        with self.assertRaises(gate0_anchor.AdmissionRefused):
            scenario.admit(P_ASCEND, out)
        with self.assertRaisesRegex(gate0_anchor.AdmissionRefused, "not in the operator's grant"):
            scenario.admit(P_MICRO, out)
        with self.assertRaisesRegex(ValueError, "settlements only"):  # reservations come from the admission only
            gate0_anchor.append(scenario.root, self.key, self.public, self.manifest_sha256, "reservation", R_ASCEND,
                                {})
        with self.assertRaisesRegex(AuthenticationError, "not the pinned operator key"):
            settle(P_ASCEND, key=Ed25519PrivateKey.generate())
        with self.assertRaisesRegex(AuthenticationError, "not the pinned operator key"):
            gate0_anchor.admit_and_reserve(scenario.root, Ed25519PrivateKey.generate(), self.public,
                                           self.manifest_sha256, R_ASCEND, {}, request=scenario.api,
                                           envelopes=self.envelopes, now=IN_WINDOW)
        self.assertEqual(len(scenario.ledger()["entries"]), 3)
        self.assertEqual(scenario.api.admitted_calls(), [P_ASCEND])
        del scenario.api.refs[scenario.api.admit_ref(1)]  # either record alone refuses a repeat: here the ledger
        with self.assertRaisesRegex(gate0_anchor.AdmissionRefused, "already in the ledger"):
            scenario.admit(P_ASCEND, out)


class AnchorTests(OperatorCase):
    """The operator's tags, each read by its exact name (astra #57025), and the launch claim (astra #57031)."""

    def test_tags_are_read_by_exact_name_and_must_bind_their_grant_manifest_and_call(self):
        scenario = self.grant()
        read = scenario.tags.read
        self.assertIsNone(read(GRANT_ID, "reserve", P_ASCEND, self.manifest_sha256))
        scenario.reserve(P_ASCEND, P_ASCEND.replace("-g64", "-g640"))  # a near name exists too
        message = read(GRANT_ID, "reserve", P_ASCEND, self.manifest_sha256)
        self.assertEqual((message["kind"], message["grant_id"], message["call"]), ("reserve", GRANT_ID, P_ASCEND))
        reads = [path for method, path in scenario.api.log if method == "GET"]
        self.assertIn("/git/ref/" + gate0_anchor.tag_ref(GRANT_ID, "reserve", P_ASCEND), reads)
        self.assertFalse(any("matching-refs" in path or path.endswith("/") for path in reads))  # no listing, no prefix
        self.assertIsNone(read(GRANT_ID, "reserve", R_ASCEND, self.manifest_sha256))
        sha = self.manifest_sha256
        wrong = {
            "another call": gate0_anchor.tag_message("reserve", GRANT_ID, sha, R_MICRO),
            "another manifest": gate0_anchor.tag_message("reserve", GRANT_ID, "0" * 64, P_MICRO),
            "another grant": gate0_anchor.tag_message("reserve", "g-other", sha, P_MICRO),
            "another kind": gate0_anchor.tag_message("settle", GRANT_ID, sha, P_MICRO, status="exited", outputs={}),
            "no JSON": "reserve " + P_MICRO,
        }
        for label, text in wrong.items():
            with self.subTest(message=label):
                api = FakeGitHub()
                commit = api("POST", "/git/commits", {"message": text, "tree": EMPTY_TREE, "parents": []})
                api("POST", "/git/refs", {"ref": api.ref("reserve", P_MICRO), "sha": commit["sha"]})
                with self.assertRaises(AuthenticationError):
                    TagReader(api).read(GRANT_ID, "reserve", P_MICRO, sha)
        settle = gate0_anchor.tag_message("settle", GRANT_ID, sha, P_MICRO, status="exited", outputs={})
        unbound = json.loads(settle)
        unbound.pop("outputs")
        scenario.tag("settle", P_MICRO, json.dumps(unbound))
        with self.assertRaisesRegex(AuthenticationError, "terminal status"):
            read(GRANT_ID, "settle", P_MICRO, sha)
        scenario.tag("launch", P_MICRO, json.dumps({**json.loads(gate0_anchor.tag_message("launch", GRANT_ID, sha,
                                                                                          P_MICRO)),
                                                    "reservation_sha256": None}))
        with self.assertRaisesRegex(AuthenticationError, "signed reservation"):
            read(GRANT_ID, "launch", P_MICRO, sha)

    def test_a_tag_that_cannot_be_read_is_never_an_absence(self):
        scenario = self.grant()
        scenario.reserve(P_ASCEND)
        for down in ({("GET", "/git/ref/")}, {("GET", "/git/commits/")}):
            with self.subTest(down=down):
                scenario.api.down = down
                with self.assertRaises(AnchorUnavailable):
                    scenario.tags.read(GRANT_ID, "reserve", P_ASCEND, self.manifest_sha256)
        scenario.api.down = {("GET", "/git/ref/")}
        with self.assertRaises(AnchorUnavailable):  # during an outage a missing tag is not confirmed absent either
            scenario.tags.read(GRANT_ID, "settle", P_ASCEND, self.manifest_sha256)
        scenario.api.down = set()
        scenario.api.refs[scenario.api.ref("settle", P_ASCEND)] = "f" * 40  # a ref whose commit cannot be read
        with self.assertRaises(AnchorUnavailable):
            scenario.tags.read(GRANT_ID, "settle", P_ASCEND, self.manifest_sha256)

    def test_the_claim_creates_once_and_never_succeeds_on_uncertainty(self):
        scenario = self.grant()

        def claim(call):
            return gate0_anchor.claim_launch(scenario.api, GRANT_ID, self.manifest_sha256, call,
                                             reservation_sha256="1" * 64)
        with self.assertRaisesRegex(ClaimRefused, "has not reserved"):
            claim(P_ASCEND)
        scenario.reserve(P_ASCEND, R_ASCEND, P_MICRO, R_MICRO)
        made = claim(P_ASCEND)
        self.assertEqual(made["ref"], gate0_anchor.tag_ref(GRANT_ID, "launch", P_ASCEND))
        launch = scenario.tags.read(GRANT_ID, "launch", P_ASCEND, self.manifest_sha256)
        self.assertEqual(launch["reservation_sha256"], "1" * 64)
        with self.assertRaisesRegex(ClaimRefused, "no launch"):  # the create-only ref: a second create fails
            claim(P_ASCEND)
        scenario.api.fail_create = {scenario.api.ref("launch", P_MICRO): "after"}
        with self.assertRaises(ClaimUncertain):
            claim(P_MICRO)
        self.assertTrue(scenario.api.has("launch", P_MICRO))  # it was made, and the caller cannot know: consumed
        scenario.api.fail_create = {scenario.api.ref("launch", R_MICRO): "before"}
        with self.assertRaises(ClaimUncertain):
            claim(R_MICRO)
        scenario.api.fail_create = {}
        scenario.api.down = {("POST", "/git/commits")}
        with self.assertRaises(AnchorUnavailable):  # no ref create was attempted
            claim(R_ASCEND)
        self.assertEqual(scenario.api.launch_tags(), [scenario.api.ref("launch", P_ASCEND),
                                                      scenario.api.ref("launch", P_MICRO)])


class GitHubClientTests(unittest.TestCase):
    """gate0_anchor.github_request against fixture responses: urlopen is replaced, so nothing reaches the network.
    An authenticated 404 for a ref is an absence; every other failure, including a 404 for a credential that cannot
    read the repository, is AnchorUnavailable; a 422 on a ref create is RefExists."""

    REPOSITORY = "Sentinelayer-AIdenID/sentilab"
    REF = "/git/ref/" + gate0_anchor.tag_ref("g", "settle", "c-1")

    def setUp(self):
        self.credential = "fixture-" + secrets.token_hex(8)  # made at run time
        self.seen = []

    def client(self, table: dict):
        def urlopen(req, timeout):
            self.seen.append((req.get_method(), req.full_url, req.get_header("Authorization"), timeout))
            answer = table.get((req.get_method(), req.full_url.split("/repos/" + self.REPOSITORY, 1)[1]), 500)
            if isinstance(answer, BaseException):
                raise answer
            if isinstance(answer, int):
                raise urllib.error.HTTPError(req.full_url, answer, "fixture", {}, None)
            return io.BytesIO(answer if isinstance(answer, bytes) else json.dumps(answer).encode("utf-8"))
        patcher = mock.patch.object(gate0_anchor.urllib.request, "urlopen", urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)
        return gate0_anchor.github_request(self.REPOSITORY, self.credential)

    def test_a_ref_is_read_by_its_exact_name_with_the_credential_in_the_header_only(self):
        found = {"ref": "refs/tags/gate0-g/settle-c-1", "object": {"type": "commit", "sha": "a" * 40}}
        request = self.client({("GET", self.REF): found})
        self.assertEqual(request("GET", self.REF), found)
        self.assertEqual(self.seen, [("GET", f"https://api.github.com/repos/{self.REPOSITORY}/git/ref/tags/gate0-g/"
                                             "settle-c-1", "Bearer " + self.credential, 15)])

    def test_only_an_authenticated_404_is_an_absence(self):
        visible = {"full_name": self.REPOSITORY}
        with self.assertRaises(AnchorAbsent):
            self.client({("GET", self.REF): 404, ("GET", ""): visible})("GET", self.REF)
        for label, repository in (("unreadable repository", 404), ("another repository", {"full_name": "a/b"}),
                                  ("repository unavailable", 500)):
            with self.subTest(case=label), self.assertRaises(AnchorUnavailable):
                self.client({("GET", self.REF): 404, ("GET", ""): repository})("GET", self.REF)
        for failure in (401, 403, 429, 500, 502, TimeoutError("timed out"), socket.timeout("timed out"),
                        urllib.error.URLError("no route"), ConnectionResetError(), b"not json"):
            with self.subTest(failure=failure):
                with self.assertRaises(AnchorUnavailable) as caught:
                    self.client({("GET", self.REF): failure, ("GET", ""): visible})("GET", self.REF)
                self.assertNotIn(self.credential, str(caught.exception))
        commit = "/git/commits/" + "a" * 40
        with self.assertRaises(AnchorUnavailable):  # only a ref's 404 can be an absence
            self.client({("GET", commit): 404, ("GET", ""): visible})("GET", commit)

    def test_a_ref_create_conflict_is_refused_and_every_other_failure_is_uncertain(self):
        body = {"ref": "refs/tags/gate0-g/launch-c-1", "sha": "b" * 40}
        with self.assertRaises(RefExists):
            self.client({("POST", "/git/refs"): 422})("POST", "/git/refs", body)
        for failure in (500, 502, 403, TimeoutError("timed out")):
            with self.subTest(failure=failure), self.assertRaises(AnchorUnavailable):
                self.client({("POST", "/git/refs"): failure})("POST", "/git/refs", body)
        reserve = gate0_anchor.tag_ref("g", "reserve", "c-1")
        table = {("GET", "/git/ref/" + reserve): {"ref": "refs/" + reserve, "object": {"type": "commit", "sha": "c" * 40}},
                 ("GET", "/git/commits/" + "c" * 40): {"sha": "c" * 40, "tree": {"sha": EMPTY_TREE},
                                                       "message": gate0_anchor.tag_message("reserve", "g", "0" * 64, "c-1")},
                 ("POST", "/git/commits"): {"sha": "d" * 40}}
        for answer, outcome in ((422, ClaimRefused), (500, ClaimUncertain), (TimeoutError("lost"), ClaimUncertain)):
            with self.subTest(create=answer), self.assertRaises(outcome):
                gate0_anchor.claim_launch(self.client({**table, ("POST", "/git/refs"): answer}), "g", "0" * 64, "c-1",
                                          reservation_sha256="1" * 64)


class RecordTests(OperatorCase):
    """Records come from the operator's signed ledger and tags by admitted call id (astra supplement 6545712065;
    warden #56856, #56967)."""

    def passing(self, label: str = "pass"):
        scenario = self.grant(label)
        scenario.fabricate(GOOD)
        return scenario, self.record(scenario)

    def test_four_required_outcomes_within_tolerance_pass_and_bind_the_binary(self):
        scenario, record = self.passing()
        self.assertEqual(record["verdict"], "PASS", (record["failures"], record["errors"], record["missing"]))
        self.assertEqual(sorted(record["calls"]), sorted(REQUIRED))
        self.assertEqual((record["missing"], record["failures"], record["errors"]), ([], [], []))
        self.assertTrue(all(r["byte_identical"] for r in record["replays"]))
        self.assertEqual((record["manifest"]["sha256"], record["grant_id"]), (self.manifest_sha256, GRANT_ID))
        self.assertEqual(record["pass_scope"]["grid"], 64)
        self.assertEqual(record["calls"][P_ASCEND]["settle_tag"]["status"], "exited")
        self.assertEqual(self.require(scenario, record)["verdict"], "PASS")
        rebuilt = self.root / "rebuilt"
        rebuilt.write_bytes(FAKE_BINARIES["hotspot6"] + b" rebuilt")
        with self.assertRaises(GateZeroRefusal):
            self.require(scenario, record, binary=rebuilt)

    def test_deferred_points_are_pending_verification_in_every_record(self):
        _, record = self.passing()
        pending = {p["reference"]: (p["paper_c"], p["status"]) for p in record["claim_scope"]["pending_verification"]}
        self.assertEqual(pending, {"ascend910-tap25d-fig6c": (75.47, "pending verification"),
                                   "micro150-tap25d-fig5c": (94.89, "pending verification")})
        self.assertEqual({c["reference"] for c in record["claim_scope"]["paper_match"]}, {ASCEND, MICRO})
        self.assertIn("not claimed", record["claim_scope"]["snapped_variants"])

    def test_a_completed_miss_fails_for_a_primary_or_a_replay_on_its_own(self):
        for name in (P_MICRO, R_MICRO):
            with self.subTest(call=name):
                scenario = self.grant(name)
                scenario.fabricate({**GOOD, name: 115.94 + 1.01})
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "FAIL")
                self.assertEqual(record["claim_scope"]["paper_match"], [])
                with self.assertRaises(GateZeroRefusal):
                    self.require(scenario, record)

    def test_a_replay_that_differs_from_its_primary_fails(self):
        scenario = self.grant()
        scenario.fabricate({**GOOD, R_ASCEND: {"peak_c": 75.09, "drop_k": 2.0}})
        record = self.record(scenario)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual({r["replay"]: r["byte_identical"] for r in record["replays"]}, {R_ASCEND: False, R_MICRO: True})

    def test_a_declared_grid_64_of_any_other_shape_is_never_pass(self):
        """astra (#56982 P2-1): matching digests over a 4x4x8, 64x64x1 or 64x64x7 grid used to PASS."""
        shapes = {"4x4x8": dict(grid=4), "64x64x1": dict(layers=1), "64x64x7": dict(layers=7),
                  "64x64x8 headerless": dict(headered=False),
                  "a block missing from the steady file": dict(omit_block="layer_3_Ubump_0")}
        for label, shape in shapes.items():
            with self.subTest(shape=label):
                scenario = self.grant(label.replace(" ", "-"))
                # both, so the replay still matches its primary byte for byte
                scenario.fabricate({**GOOD, P_ASCEND: {"peak_c": GOOD[P_ASCEND], **shape},
                                    R_ASCEND: {"peak_c": GOOD[R_ASCEND], **shape}})
                record = self.record(scenario)
                self.assertIn(record["verdict"], ("INCOMPLETE", "FAIL"))
                self.assertEqual({m["call"] for m in record["missing"]}, {P_ASCEND, R_ASCEND})
                self.assertTrue(all("strict evaluator-bound reader" in m["reason"] for m in record["missing"]))
                with self.assertRaises(GateZeroRefusal):
                    self.require(scenario, record)
        scenario, record = self.passing("control")  # the same path at the real shape: 64 x 64, 8 headered layers
        self.assertEqual(record["verdict"], "PASS", record["missing"])
        self.assertEqual(record["calls"][P_ASCEND]["diagnostics"]["grid"], {"n": 64, "layers_in_file": list(range(8))})
        self.assertEqual(self.require(scenario, record)["verdict"], "PASS")

    def test_withholding_or_failing_a_required_call_gives_incomplete_never_pass(self):
        """astra's control: omitting the failed point used to turn FAIL into PASS."""
        scenario = self.grant("fail")
        scenario.fabricate({**GOOD, P_ASCEND: 80.0})
        self.assertEqual(self.record(scenario)["verdict"], "FAIL")
        scenario = self.grant("withheld")
        scenario.fabricate({**GOOD, P_ASCEND: 80.0})
        scenario.api.drop("settle", P_ASCEND)  # the operator never writes the failed call's settle tag
        record = self.record(scenario)
        self.assertEqual(record["verdict"], "INCOMPLETE")
        self.assertEqual([m["call"] for m in record["missing"]], [P_ASCEND])
        self.assertIn("no settle tag", record["missing"][0]["reason"])
        with self.assertRaises(GateZeroRefusal):
            self.require(scenario, record)
        for status, code in (("wall_timeout", None), ("cpu_limit", -9), ("launch_error", None), ("record_error", 0),
                             ("runtime_changed", 0), ("setup_error", None), ("claim_uncertain", None),
                             ("claim_refused", None), ("exited", 7)):
            with self.subTest(settled=status, exit_status=code):
                scenario = self.grant(f"{status}-{code}")
                scenario.fabricate(GOOD, settled={R_MICRO: (status, code)})
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "INCOMPLETE")
                self.assertIn(f"exit status {code!r}", next(m["reason"] for m in record["missing"]
                                                            if m["call"] == R_MICRO))
        scenario = self.grant("only-three")
        scenario.fabricate({k: v for k, v in GOOD.items() if k != R_ASCEND})
        self.assertEqual(self.record(scenario)["verdict"], "INCOMPLETE")
        scenario = self.grant("not-granted", calls=[c for c in self.calls if c != R_MICRO])
        scenario.fabricate({k: v for k, v in GOOD.items() if k != R_MICRO})
        record = self.record(scenario)
        self.assertEqual((record["verdict"], [m["call"] for m in record["missing"]]), ("INCOMPLETE", [R_MICRO]))

    def test_a_primary_and_its_replay_keep_separate_identities_and_outcomes(self):
        """astra: keyed by reference, the replay directory silently replaced the primary."""
        _, record = self.passing()
        self.assertNotEqual(record["calls"][P_ASCEND]["run_dir"], record["calls"][R_ASCEND]["run_dir"])
        self.assertEqual((record["calls"][P_ASCEND]["role"], record["calls"][R_ASCEND]["role"]), ("primary", "replay"))
        for collision in ("the primary's own directory", "a copy of the primary's directory"):
            with self.subTest(collision=collision):
                # A key holder's consistent forgery: the replay is reserved and settled on the primary's run.
                scenario = self.grant(collision.replace(" ", "-").replace("'", ""))
                scenario.fabricate({k: v for k, v in GOOD.items() if k != R_ASCEND})
                primary = scenario.run_dir(P_ASCEND)
                if collision.startswith("a copy"):
                    shutil.copytree(primary, primary.with_name("copied-primary"))
                    primary = primary.with_name("copied-primary")
                reservation = scenario.admit(R_ASCEND, primary)
                gate0_anchor.claim_launch(scenario.api, GRANT_ID, self.manifest_sha256, R_ASCEND,
                                          reservation_sha256=gate0_anchor.digest(reservation))
                settled = scenario.entries(P_ASCEND)["settlement"]
                gate0_anchor.append(scenario.root, self.key, self.public, self.manifest_sha256, "settlement",
                                    R_ASCEND, {k: settled[k] for k in ("status", "exit_status", "outputs",
                                                                         "receipt_sha256", "charged_cpu_s")})
                scenario.settle(R_ASCEND)
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "FAIL")
                self.assertIn("does not hold this admitted call's receipt",
                              next(f["reason"] for f in record["failures"] if f["call"] == R_ASCEND))

    def test_editing_a_fail_record_never_unlocks(self):
        """astra #56837: an edited simulated value or verdict on a FAIL record must not unlock search."""
        scenario = self.grant()
        scenario.fabricate({P_ASCEND: 122.32, R_ASCEND: 122.32, P_MICRO: 229.35, R_MICRO: 229.35})
        record = self.record(scenario)
        forged = json.loads(json.dumps(record))
        forged["verdict"] = "PASS"
        for result in forged["calls"].values():
            result["simulated_c"], result["delta_k"], result["within_tolerance"] = result["paper_c"], 0.0, True
        with self.assertRaises(GateZeroRefusal):
            self.require(scenario, forged)
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", hotspot_binary=self.binaries["hotspot6"], gate_zero_record=forged,
                        ledger_root=scenario.root, tags=scenario.tags)

    def test_evidence_edited_after_settlement_is_refused(self):
        scenario, record = self.passing("output")
        steady = scenario.run_dir(P_ASCEND) / "sample.steady"
        steady.write_text(steady.read_text() + "layer_4_WS_9\t330.00\n", encoding="utf-8")
        with self.assertRaisesRegex(GateZeroRefusal, "differs from its receipt digest"):
            self.require(scenario, record)
        scenario, record = self.passing("receipt")
        receipt = scenario.run_dir(P_ASCEND) / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"grid": 64', '"grid":  64'), encoding="utf-8")
        with self.assertRaisesRegex(GateZeroRefusal, "changed after the call settled"):
            self.require(scenario, record)
        scenario, record = self.passing("stored")
        stale = json.loads(json.dumps(record))
        stale["calls"][P_MICRO]["receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(GateZeroRefusal, "changed after the record was made"):
            self.require(scenario, stale)

    def test_receipts_must_bind_every_digest_the_manifest_the_grant_and_the_raw_identity(self):
        edits = {
            "drop grid digest": (lambda r: r["outputs"].pop("sample.grid.steady"), "differs from its receipt digest"),
            "wrong steady digest": (lambda r: r["outputs"].update({"sample.steady": "0" * 64}), "receipt digest"),
            "unbound input": (lambda r: r["inputs"].update({"new_hotspot.config": "0" * 64}), "does not bind"),
            "other manifest": (lambda r: r.update(manifest_sha256="0" * 64), "another manifest, grant or reservation"),
            "other grant": (lambda r: r.update(grant_id="g-other"), "another manifest, grant or reservation"),
            "other reservation": (lambda r: r.update(reservation_sha256="0" * 64), "another manifest, grant"),
            "snapped identity": (lambda r: r.update(layout_identity="snapped"), "only the pinned raw layout"),
            "other raw layout": (lambda r: r.update(raw_layout_sha256="0" * 64), "only the pinned raw layout"),
            "other binary": (lambda r: r["evaluator"].update(binary_sha256="0" * 64), "different evaluator binary"),
            "grid 32": (lambda r: r.update(grid=32), "another engine or grid"),
            "other call": (lambda r: r.update(call=R_ASCEND), "does not hold this admitted call's receipt"),
            "other status": (lambda r: r.update(status="wall_timeout"), "receipt and its settlement disagree"),
        }
        for label, (change, reason) in edits.items():
            with self.subTest(edit=label):
                scenario = self.grant(label.replace(" ", "-"))
                scenario.fabricate(GOOD, edit={P_ASCEND: change})
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "FAIL")
                self.assertIn(reason, next(f["reason"] for f in record["failures"] if f["call"] == P_ASCEND))
        scenario = self.grant("stale-config")
        scenario.fabricate(GOOD)
        config = scenario.run_dir(P_ASCEND) / "new_hotspot.config"
        config.write_text(config.read_text().replace("0.011111111111111112", "0.1"))
        self.assertEqual(self.record(scenario)["verdict"], "FAIL")

    def test_the_drop_and_the_stack_are_reported_not_asserted(self):
        scenario = self.grant()
        scenario.fabricate({**GOOD, P_ASCEND: {"peak_c": 75.09, "drop_k": 51.0},
                            R_ASCEND: {"peak_c": 75.09, "drop_k": 51.0}})
        record = self.record(scenario)
        self.assertEqual(record["verdict"], "PASS")
        diagnostics = record["calls"][P_ASCEND]["diagnostics"]
        drop = diagnostics["spreader_sink_drop"]
        self.assertAlmostEqual(drop["drop_K"], 51.5, places=6)  # 51 K of link plus the synthetic 0.5 K per layer
        self.assertIn("copper predicts about 1-2 K", drop["expectation"])
        (stack,) = diagnostics["same_index_stack"]
        self.assertEqual(stack["at"], {"row": 16, "col": 16})
        self.assertEqual([layer["layer"] for layer in stack["layers"]], [4, 5, 6, 7])
        self.assertEqual([layer["name"] for layer in stack["layers"]][2:], ["spreader", "sink"])
        self.assertAlmostEqual(stack["drops"][-1]["drop_K"], 0.5 + 51.0, places=6)

    def test_only_the_native6_engine_can_pass_and_only_at_grid_64(self):
        scenario, record = self.passing()
        with self.assertRaisesRegex(GateZeroRefusal, "covers grid 64 only"):
            self.require(scenario, record, grid=32)
        for kind in ("hotspot7_default", "material_only"):
            with self.assertRaisesRegex(GateZeroRefusal, "judges hotspot6 only"):
                self.record(scenario, self.binaries[kind], kind=kind)
        with self.assertRaises(GateZeroRefusal):
            self.require(scenario, None)
        other = json.loads(json.dumps(record))
        other["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GateZeroRefusal, "another manifest"):
            self.require(scenario, other)


class AuthenticityTests(OperatorCase):
    """warden #56967 P2-1 and the anchor (warden and astra #57024, #57025): without the operator's key nothing
    verifies; the tags and the ledger must agree; a missing tag is INCOMPLETE and an unreadable one ERROR."""

    def test_a_ledger_fabricated_without_the_operator_key_never_passes(self):
        attacker = Ed25519PrivateKey.generate()
        forged = self.grant("forged", signer=attacker)  # every file and every tag, but the attacker's key
        forged.fabricate(GOOD)
        record = self.record(forged)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertIn("cannot be verified", record["failures"][0]["reason"])
        self.assertEqual(record["calls"], {})
        with self.assertRaises(GateZeroRefusal):
            self.require(forged, record)
        receipts = self.grant("receipts")  # the operator's ledger, receipts signed by someone else
        receipts.fabricate(GOOD, receipt_signer=attacker)
        record = self.record(receipts)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual({f["call"] for f in record["failures"]}, set(REQUIRED))
        unsigned = self.grant("unsigned")
        unsigned.fabricate(GOOD)
        for path in unsigned.dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("signature")
            path.chmod(0o644)
            path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.record(unsigned)["verdict"], "FAIL")

    def test_a_missing_settle_tag_is_incomplete_and_an_unreadable_tag_is_error(self):
        scenario = self.grant()
        scenario.fabricate(GOOD)
        self.assertEqual(self.record(scenario)["verdict"], "PASS")
        for down in ({("GET", "/git/ref/")}, {("GET", "/git/commits/")}):
            with self.subTest(down=down):
                scenario.api.down = down
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "ERROR")
                self.assertEqual({e["call"] for e in record["errors"]}, set(REQUIRED))
                self.assertEqual((record["missing"], record["claim_scope"]["paper_match"]), ([], []))
                with self.assertRaisesRegex(GateZeroRefusal, "is ERROR"):
                    self.require(scenario, record)
        scenario.api.down = set()
        scenario.api.drop("settle", R_MICRO)
        record = self.record(scenario)
        self.assertEqual((record["verdict"], [m["call"] for m in record["missing"]]), ("INCOMPLETE", [R_MICRO]))
        scenario.fabricate({P_MICRO.replace("p-hs6", "p-hs7"): 116.0})  # a comparator call settles; nothing changes
        self.assertEqual(self.record(scenario)["verdict"], "INCOMPLETE")

    def test_a_ledger_that_disagrees_with_the_tags_fails(self):
        def rolled_back(scenario):  # a valid prefix: the last settlement removed
            last = sorted(scenario.dir.glob("*.json"))[-1]
            last.unlink()

        def replaced(scenario):  # the operator's own key reopens an identical grant on an empty ledger
            shutil.rmtree(scenario.root)
            Scenario(self, "replaced", api=scenario.api)

        def retagged(scenario):  # a settle tag that binds other hashes
            scenario.api.drop("settle", P_ASCEND)
            scenario.tag("settle", P_ASCEND, gate0_anchor.tag_message("settle", GRANT_ID, self.manifest_sha256,
                                                                       P_ASCEND, status="exited",
                                                                       receipt_sha256="0" * 64, outputs={},
                                                                       charged_cpu_s=6.0))

        def relaunched(scenario):  # a launch tag that binds another reservation
            scenario.api.drop("launch", P_ASCEND)
            scenario.tag("launch", P_ASCEND, gate0_anchor.tag_message("launch", GRANT_ID, self.manifest_sha256,
                                                                       P_ASCEND, reservation_sha256="0" * 64))
        def unanchored(scenario):  # a reservation whose admission tag is gone
            del scenario.api.refs["refs/" + scenario.entries(P_ASCEND)["reservation"]["admission"]["ref"]]
        controls = {"valid-prefix rollback": rolled_back, "whole-ledger deletion": lambda s: shutil.rmtree(s.root),
                    "no admission tag": unanchored,
                    "replaced ledger": replaced, "settle tag rebound": retagged, "launch tag rebound": relaunched,
                    "no launch claim": lambda s: s.api.drop("launch", P_ASCEND),
                    "no reserve tag": lambda s: s.api.drop("reserve", P_ASCEND)}
        for label, change in controls.items():
            with self.subTest(control=label):
                scenario = self.grant("replaced" if label == "replaced ledger" else label.replace(" ", "-"))
                scenario.fabricate(GOOD)
                change(scenario)
                record = self.record(scenario)
                self.assertEqual(record["verdict"], "FAIL", record["missing"])
                self.assertEqual(record["claim_scope"]["paper_match"], [])
                if label in ("no launch claim", "no reserve tag"):
                    self.assertIn("without the operator's reserve tag or the launch claim",
                                  next(f["reason"] for f in record["failures"] if f["call"] == P_ASCEND))
        scenario = self.grant("copied")
        scenario.fabricate(GOOD)
        elsewhere = self.root / "copied-elsewhere"
        shutil.copytree(scenario.root, elsewhere)  # cross-directory reuse
        record = build_record("hotspot6", self.binaries["hotspot6"], ledger_root=elsewhere, tags=scenario.tags)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertIn("another ledger directory", record["failures"][0]["reason"])

    def test_the_record_needs_the_operators_ledger_root_and_tag_credential(self):
        with self.assertRaisesRegex(GateZeroRefusal, "not configured"):
            build_record("hotspot6", self.binaries["hotspot6"], tags=TagReader(FakeGitHub()))
        scenario = self.grant()
        with self.assertRaisesRegex(GateZeroRefusal, "GH_TOKEN"):
            build_record("hotspot6", self.binaries["hotspot6"], ledger_root=scenario.root)
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", hotspot_binary=self.binaries["hotspot6"], gate_zero_record={
                "schema": gate_zero.RECORD_SCHEMA, "references_sha256": PINNED_REFERENCES_SHA256})


class ReportTests(OperatorCase):
    """astra (#56982 P2-3): report verifies every binding first and derives its diagnostics from the raw files."""

    def test_report_derives_diagnostics_from_verified_raw_evidence_not_a_stored_record(self):
        scenario = self.grant()
        fabricated = {"active_layer_grid_peak": {"peak_C": 999.0}, "spreader_sink_drop_diagnostic": {"drop_K": 0.0},
                      "same_index_stack_at_active_argmax": []}
        scenario.fabricate(GOOD, edit={P_ASCEND: lambda r: r.update(solve_record=fabricated)})  # signed, bound
        report = reference_validation.report(ledger_root=scenario.root, tags=scenario.tags)
        entry = next(e for e in report["calls"] if e["call"] == P_ASCEND)
        self.assertTrue(entry["usable"])
        self.assertAlmostEqual(entry["grid_peak_c"], 379.0 - 273.15, places=6)  # the raw grid, not the 999.0 stored
        self.assertAlmostEqual(entry["drop"]["drop_K"], 1.5, places=6)  # the synthetic 1 K link plus 0.5 K
        self.assertEqual(entry["stack"][0]["at"], {"row": 16, "col": 16})
        row = next(r for r in report["rows"] if r["kind"] == "hotspot6" and r["reference"] == ASCEND)
        self.assertTrue(row["replay_byte_identical"])
        self.assertEqual(report["grant_id"], GRANT_ID)

    def test_every_unusable_call_is_listed_with_its_reason(self):
        scenario = self.grant()
        scenario.fabricate({**GOOD, R_ASCEND: {"peak_c": GOOD[R_ASCEND], "grid": 4}}, settled={R_MICRO: ("exited", 7)},
                           edit={P_MICRO: lambda r: r["outputs"].update({"sample.steady": "0" * 64})})
        receipt = scenario.run_dir(P_ASCEND) / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"grid": 64', '"grid":  64'), encoding="utf-8")  # unbound edit
        report = reference_validation.report(ledger_root=scenario.root, tags=scenario.tags)
        reasons = {item["call"]: item["reason"] for item in report["not_completed"]}
        self.assertEqual(len(reasons), 12)  # nothing usable: four unusable, eight never settled
        self.assertIn("changed after the call settled", reasons[P_ASCEND])
        self.assertIn("differs from its receipt digest", reasons[P_MICRO])
        self.assertIn("exit status 7", reasons[R_MICRO])
        self.assertIn("strict evaluator-bound reader", reasons[R_ASCEND])
        self.assertEqual(sum("no settle tag" in reason for reason in reasons.values()), 8)
        self.assertFalse(any(e["usable"] for e in report["calls"]))
        self.assertTrue(all(row["block_centre_c"]["64"] is None for row in report["rows"]))
        manifest = json.loads(self.manifest_path.read_text())
        manifest["operator"]["public_key_ed25519"] = gate0_anchor.public_key_hex(Ed25519PrivateKey.generate())
        self.manifest_path.write_bytes(slab049._dump(manifest))  # a swapped key in the file is never trusted
        with self.assertRaisesRegex(CallRefused, "not what this tree generates"):
            reference_validation.report(ledger_root=scenario.root, tags=scenario.tags)


class SelectorAndOracleTests(OperatorCase):
    """Search and headroom need a PASS at grid 64; the selector keeps HotSpot 7's oracle unchanged."""

    def test_search_and_headroom_refuse_without_a_pass_or_off_grid_64(self):
        for purpose in ("search", "headroom"):
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot6", purpose, hotspot_binary=self.binaries["hotspot6"])
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot7", purpose, hotspot_binary=self.binaries["hotspot7_default"])
        scenario = self.grant()
        scenario.fabricate(GOOD)
        record = self.record(scenario)
        with self.assertRaisesRegex(GateZeroRefusal, "covers a 64 x 64 grid only"):
            make_oracle("hotspot6", "search", 32, 32, hotspot_binary=self.binaries["hotspot6"], gate_zero_record=record,
                        ledger_root=scenario.root, tags=scenario.tags)
        with self.assertRaises(ValueError):
            make_oracle("hotspot6", "validate-reference", hotspot_binary=self.binaries["hotspot6"])

    def test_a_pass_unlocks_search_with_a_new_identity_and_hotspot7_stays_locked(self):
        binary = self.binaries["hotspot6"]
        scenario = self.grant()
        scenario.fabricate(GOOD)
        record = self.record(scenario)
        oracle = make_oracle("hotspot6", "search", hotspot_binary=binary, gate_zero_record=record,
                             ledger_root=scenario.root, tags=scenario.tags)
        self.assertIsInstance(oracle, HotSpot6Oracle)
        self.assertEqual((oracle.grid_rows, oracle.grid_cols), (64, 64))
        base = HotSpotOracle(64, 64, hotspot_binary=binary)
        self.assertEqual(oracle.base_problem_hash, base.problem_hash)
        self.assertNotEqual(oracle.problem_hash, base.problem_hash)
        self.assertTrue(oracle.solver_version.startswith(f"HotSpot-6.0:{gate_zero.HOTSPOT6_COMMIT}+SLAB-049:"))
        self.assertTrue(base.solver_version.startswith("HotSpot-7:"))
        with self.assertRaises(GateZeroRefusal):  # native7 is the comparator: no record can pass it here
            make_oracle("hotspot7", "headroom", hotspot_binary=self.binaries["hotspot7_default"],
                        gate_zero_record=record, ledger_root=scenario.root, tags=scenario.tags)

    def test_hotspot6_oracle_refuses_evaluations_and_the_wrong_binary(self):
        oracle = HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6"])
        design = oracle.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        with self.assertRaises(GateZeroRefusal):
            asyncio.run(oracle(design))
        with self.assertRaises(HotSpotOracleError):
            HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6_tap_faithful"])

    def test_hotspot6_results_are_labelled_hotspot6_never_hotspot7(self):
        """warden #56856 P3: the HotSpot 6.0 evidence label was untested."""
        with mock.patch("sundai_hotspot.evaluators.require_gate_zero", return_value={"verdict": "PASS"}):
            oracle = HotSpot6Oracle(4, 4, hotspot_binary=self.binaries["hotspot6"])
        design = oracle.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        response = {
            "candidate_hash": design.hash, "problem_hash": oracle.problem_hash,
            "binary_sha256": oracle.problem.hotspot_binary_sha256, "grid_rows": 4, "grid_cols": 4,
            "heatmap_c": [[60.0] * 4 for _ in range(4)], "maximum_temperature_c": 60.0, "all_layers_peak_c": 60.0,
            "solver_seconds": 0.1, "input_generation_seconds": 0.01,
            "input_sha256": {name: "a" * 64 for name in slab049.REFERENCE_INPUTS},
        }

        async def evaluate_once():
            try:
                return await oracle(design)
            finally:
                await oracle.aclose()

        with mock.patch("sundai_hotspot.tap_oracle._run_worker", new_callable=mock.AsyncMock, return_value=response):
            result = asyncio.run(evaluate_once())
        self.assertTrue(result.evidence_kind.startswith(EVIDENCE_PREFIX + "steady-state TAP"), result.evidence_kind)
        self.assertNotIn("HotSpot 7", result.evidence_kind)
        self.assertTrue(result.solver_version.startswith("HotSpot-6.0:"))
        relabelled = mock.Mock(evidence_kind="steady-state TAP from some future label")
        with mock.patch.object(HotSpotOracle, "_result_from_response", return_value=relabelled):
            with self.assertRaises(HotSpotOracleError):
                oracle._result_from_response(response, design, (), 0.0)


class ManifestTests(unittest.TestCase):
    """warden #56856, #56967 and astra's supplement: the manifest is the tree's, every row explicit, the true worst
    case inside the binding cap, and the code-versus-supervisor split published."""

    def test_the_prior_snapped_manifest_is_byte_identical_and_never_executable(self):
        prior = REPO_ROOT / slab049.PRIOR_MANIFEST["path"]
        self.assertEqual(_sha256(prior), slab049.PRIOR_MANIFEST["sha256"])
        self.assertEqual(_sha256(REPO_ROOT / slab049.PRIOR_MANIFEST["description"]),
                         slab049.PRIOR_MANIFEST["description_sha256"])
        self.assertEqual(json.loads(prior.read_text())["schema"], slab049.PRIOR_MANIFEST["schema"])
        with self.assertRaisesRegex(slab049.ManifestMismatch, "prior snapped manifest"):
            slab049.check_manifest(prior.read_bytes())
        self.assertNotEqual(slab049.MANIFEST_PATH.resolve(), prior.resolve())

    def test_the_committed_manifest_is_what_the_tree_generates_and_drift_is_refused(self):
        committed = slab049.MANIFEST_PATH.read_bytes()
        manifest = slab049.check_manifest(committed)  # the committed bytes, not a fresh object against itself
        self.assertEqual(sorted(manifest["source"]["generator_sha256"]),
                         sorted(slab049.GENERATOR_SOURCES + slab049.GENERATOR_DATA))
        for path, digest in manifest["source"]["generator_sha256"].items():
            self.assertEqual(_sha256(REPO_ROOT / path), digest, path)
        altered = json.loads(committed)
        altered["source"]["generator_sha256"]["sundai_tap/fastSA.py"] = "0" * 64
        with self.assertRaisesRegex(slab049.ManifestMismatch, "fastSA.py"):
            slab049.check_manifest(slab049._dump(altered))
        real = slab049._file_sha256

        def drifted(path, root=REPO_ROOT):
            return "f" * 64 if path == "sundai_tap/passive_interposer.py" else real(path, root)
        with mock.patch.object(slab049, "_file_sha256", side_effect=drifted):
            with self.assertRaisesRegex(slab049.ManifestMismatch, "passive_interposer.py"):
                slab049.check_manifest(committed)
            with self.assertRaises(CallRefused):
                reference_validation.load_manifest()

    def test_the_operator_key_is_pinned_and_the_anchor_is_published(self):
        manifest = slab049.check_manifest(slab049.MANIFEST_PATH.read_bytes())
        operator, anchor, ledger = manifest["operator"], manifest["anchor"], manifest["ledger"]
        # warden's operator key, pinned by a reviewed commit before the grant: the raw public key in hex
        pinned = "aedce64bbc007b3538c02d302da9cedbce1465c409efac8589477284bdbd2132"
        self.assertEqual((slab049.OPERATOR_PUBLIC_KEY, operator["public_key_ed25519"]), (pinned, pinned))
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pinned))  # a valid Ed25519 public key
        self.assertEqual(operator["status"], "pinned")
        self.assertIn("never lives in the repository", operator["custody"])
        self.assertEqual((anchor["repository"], anchor["namespace"], anchor["message_schema"]),
                         ("Sentinelayer-AIdenID/sentilab", "refs/tags/gate0-<grant-id>/", gate0_anchor.TAG_SCHEMA))
        self.assertEqual(sorted(anchor["tags"]), ["admit-<NN>", "launch-<call-id>", "reserve-<call-id>",
                                                  "settle-<call-id>"])
        self.assertIn("SLAB049_ANCHOR_TOKEN", anchor["credentials"]["claim"])
        self.assertEqual(ledger["dir"], "<SLAB049_LEDGER_ROOT>/slab049-<this manifest's SHA-256>")

    def test_every_row_carries_its_call_id_its_own_timeout_and_the_operator_arguments(self):
        manifest = slab049.build_call_list()
        for call in manifest["calls"]:
            argv = call["command"].split("reference_validation ", 1)[1]
            for placeholder, value in (("<fresh empty dir>", "OUT"), ("<operator ledger root>", "ROOT"),
                                       ("<operator key file>", "KEY")):
                argv = argv.replace(placeholder, value)
            with mock.patch.object(reference_validation, "validate_call") as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                run.return_value = {"status": "exited", "exit_status": 0}
                self.assertEqual(reference_validation.main(argv.split()), 0)
            self.assertEqual(run.call_args.args[0], call["id"])
            self.assertEqual(run.call_args.kwargs["timeout_s"], call["timeout_s"])
            self.assertEqual((run.call_args.kwargs["ledger_root"], run.call_args.kwargs["operator_key_path"]),
                             (Path("ROOT"), Path("KEY")))
            self.assertEqual(call["timeout_s"], {64: 50.0, 32: 15.0}[call["grid"]])
            self.assertEqual(call["cpu_limit_s"], int(call["timeout_s"]))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):  # no default timeout
            reference_validation.main(["validate-reference", "--call", REQUIRED[0], "--out", "OUT"])

    def test_the_true_worst_case_comes_from_the_limits_and_fits_the_binding_cap(self):
        """warden #56967 P2-3: every child under RLIMIT_CPU and a wall limit; the worst case is computed from them."""
        accounting = slab049.build_call_list()["accounting"]
        self.assertEqual((accounting["calls"], accounting["grid64_calls"], accounting["grid32_calls"]), (12, 8, 4))
        limits = accounting["limits"]
        self.assertEqual(limits, {"generator_cpu_s": slab049.GENERATOR_CPU_LIMIT_S,
                                  "generator_wall_s": slab049.GENERATOR_TIMEOUT_S, "loader_listings": 2,
                                  "loader_listing_cpu_s": provenance.LOADER_CPU_LIMIT_S,
                                  "loader_listing_wall_s": provenance.LOADER_TIMEOUT_S,
                                  "parent_allowance_cpu_s": slab049.PARENT_ALLOWANCE_CPU_S, "reap_s": 0.25,
                                  "settlement_tail_s": 0.25})
        self.assertEqual((limits["generator_cpu_s"], limits["generator_wall_s"]), (3, 30))
        self.assertEqual(accounting["per_call_reserve_cpu_s"], 3 + 2 * 1 + 3 + 0.25 + 0.25)
        self.assertEqual(accounting["worst_case_cpu_s"], 8 * (50 + 8.5) + 4 * (15 + 8.5))
        self.assertEqual(accounting["worst_case_cpu_s"], 562.0)
        self.assertIn("8 x (50 + 8.5) + 4 x (15 + 8.5) = 468 + 94 = 562 CPU-s", accounting["arithmetic"])
        self.assertTrue(accounting["arithmetic"].endswith("(by component: 460 CPU-s of solver limits + 102 CPU-s of "
                                                          "per-call reserves)"), accounting["arithmetic"])
        self.assertIn("from 60 to 50 s", accounting["limits_lowered"])
        self.assertIn("soft = hard", accounting["worst_case_label"])
        self.assertEqual((accounting["manifest_cpu_cap_s"], accounting["room_envelope_cpu_s"]), (600.0, 1800.0))
        self.assertIn("600 CPU-s, binds", accounting["binding_cap"])
        rows = slab049.build_call_list()["calls"]
        self.assertEqual(sum(c["accounting"]["reserved_cpu_s"] for c in rows), 562.0)
        with mock.patch.dict(slab049.TIMING, {"grid64_timeout_s": 60.0}):  # the old timeout: 642 CPU-s
            with self.assertRaisesRegex(ValueError, "642 CPU-s, exceeds the manifest cap"):
                slab049.build_call_list()
        with mock.patch.object(slab049, "GENERATOR_CPU_LIMIT_S", 10):  # the old generator limit: 646 CPU-s
            with self.assertRaisesRegex(ValueError, "exceeds the manifest cap"):
                slab049.build_call_list()

    def test_the_enforcement_split_is_published(self):
        enforcement = slab049.build_call_list()["enforcement"]
        self.assertEqual(enforcement["in_code_at_entry"], list(slab049.IN_CODE_AT_ENTRY))
        in_code = " ".join(enforcement["in_code_at_entry"])
        for rule in ("CREATES gate0-<grant>/launch-<call>", "Only a successful create launches",
                     "no admission on uncertainty", "never reclaimed", "admit-<NN>", "before any process work",
                     "accounting from the first step", "RLIMIT_CPU", "ERROR", "INCOMPLETE"):
            self.assertIn(rule, in_code)
        contract = " ".join(enforcement["operator_supervisor_contract"])
        for duty in ("key custody", "never enters the repository", "create-only", "SLAB049_ANCHOR_TOKEN",
                     "cumulative CPU budget", "process group", "protected runtime image", "trusted clock",
                     "1,800 CPU-s"):
            self.assertIn(duty, contract)


class ExecutedSetTests(OperatorCase):
    """warden #56967 P2-4: the manifest pins only what the calls execute or read, derived by tracing, so an unrelated
    edit keeps a PASS and an edit to an executed file voids it."""

    def test_the_pinned_set_is_exactly_what_the_generator_imports_and_reads(self):
        for reference in gate_zero.GATE_REFERENCES:
            with self.subTest(reference=reference.id):
                traced = slab049.trace_generator(slab049.reference_spec(reference.id))
                self.assertEqual(traced, {"imports": sorted(slab049.GENERATOR_SOURCES),
                                          "reads": sorted(slab049.GENERATOR_DATA), "spawns": [],
                                          "rlimit_cpu": [slab049.GENERATOR_CPU_LIMIT_S] * 2})
        self.assertEqual(sorted(self.manifest["source"]["generator_sha256"]),
                         sorted(slab049.GENERATOR_SOURCES + slab049.GENERATOR_DATA))
        self.assertIn("trace_generator", self.manifest["source"]["derivation"])

    def test_an_unrelated_edit_keeps_a_pass_and_an_edit_to_an_executed_file_voids_it(self):
        scenario = self.grant()
        scenario.fabricate(GOOD)
        record = self.record(scenario)
        self.assertEqual(record["verdict"], "PASS")
        tree = self.root / "tree"  # a tree holding the executed files and nothing else generates the same manifest
        for path in slab049.GENERATOR_SOURCES + slab049.GENERATOR_DATA + ("sundai_tap/routing.py",
                                                                        "sundai_hotspot/evaluators.py"):
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / path, tree / path)
        with mock.patch.object(slab049, "EXECUTED_ROOT", tree):
            self.assertEqual(slab049._dump(slab049.build_call_list()), self.manifest_path.read_bytes())
            for unrelated in ("sundai_tap/routing.py", "sundai_hotspot/evaluators.py"):  # evaluators.py was pinned
                with (tree / unrelated).open("a", encoding="utf-8") as handle:
                    handle.write("\n# an unrelated edit\n")
            self.assertEqual(self.require(scenario, record)["verdict"], "PASS")
            with (tree / "sundai_tap/fastSA.py").open("a", encoding="utf-8") as handle:  # imported by the generator
                handle.write("\n# an edit to an executed file\n")
            with self.assertRaisesRegex(GateZeroRefusal, r"source pins differ for \['sundai_tap/fastSA.py'\]"):
                self.require(scenario, record)
            with self.assertRaisesRegex(CallRefused, "fastSA.py"):
                reference_validation.load_manifest()


FAKE_SOLVER = r'''#!PYTHON
# Test-only stand-in for a HotSpot binary: identity markers in this comment, synthetic outputs, no physics.
# markers: Unit	Steady(Kelvin) dgssv SENTILAB_EVALUATOR=hotspot6@a7a3286e;grid_dump=all_layers;ticket=SLAB-049
import json, os, resource, subprocess, sys, time
open("argv0.txt", "w").write(os.path.realpath(sys.argv[0]))
case = json.load(open("CONTROL")).get(os.path.basename(os.getcwd()), {})
args = sys.argv[1:]
grid = int(args[args.index("-grid_rows") + 1]) if "-grid_rows" in args else 64
peak = float(case.get("peak_c", 75.3)) + 273.15
open("rlimit_cpu.txt", "w").write("%d %d" % resource.getrlimit(resource.RLIMIT_CPU))
if case.get("sleep"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open("child.pid", "w").write(str(child.pid))
    time.sleep(120)
tokens = [line.split()[0] for line in open("samplelayers.lcf") if line.split() and not line.startswith("#")]
steady = []
for offset in range(0, len(tokens), 7):  # every unit of every LCF layer, as HotSpot writes them
    number, floorplan = int(tokens[offset]), tokens[offset + 6]
    for line in open(floorplan):
        if line.strip() and not line.startswith("#"):
            name = line.split()[0]
            hot = number == 4 and name == "Chiplet_0"
            steady.append("layer_%d_%s\t%.2f" % (number, name, peak - (0 if hot else 5 + number)))
steady += ["hsp_TIM\t%.2f" % (peak - 30), "hsink_TIM\t%.2f" % (peak - 40), "inode_0\t320.00"]
open("sample.steady", "w").write("\n".join(steady) + "\n")
layers = 1 if case.get("truncate") else 8
with open("sample.grid.steady", "w") as out:
    for layer in range(layers):
        out.write("Layer %d:\n" % layer)
        for cell in range(grid * grid):
            out.write("%d\t%.2f\n" % (cell, peak - 1 - layer if cell else peak - layer))
print("Unit\tSteady(Kelvin)")
print("\n".join(steady))
'''


def _process_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    with open(f"/proc/{pid}/stat", encoding="ascii") as stat:  # a zombie awaiting init is already dead
        return stat.read().rsplit(")", 1)[1].split()[0] == "Z"


@unittest.skipUnless(os.name == "posix" and platform.machine() == "x86_64",
                     "the manifest lists an x86_64 POSIX host; the fake solver is a POSIX script")
class EntryCase(OperatorCase):
    """validate-reference, the real admission and launch entrypoint, on a grant host in miniature: the operator's
    runtime key and ledger, the in-memory tag API, and a Python script standing in for HotSpot (no solver runs).
    CI_ALLOCATION is cleared here: the CI image sets it, and validate-reference refuses to run under it."""

    def setUp(self):
        super().setUp()
        self.fake = self.root / "fake-hotspot6"
        self.control = self.root / "control.json"
        self.fake.write_text(FAKE_SOLVER.replace("PYTHON", sys.executable).replace("CONTROL", str(self.control)),
                             encoding="utf-8")
        self.fake.chmod(0o755)
        self.control.write_text("{}", encoding="utf-8")
        self.write_provenance(self.fake)
        self.scenario = self.grant()

    def write_provenance(self, binary: Path, kind: str = "hotspot6") -> None:
        record = provenance.build_provenance(kind, binary)
        provenance.provenance_path(binary).write_text(json.dumps(record), encoding="utf-8")

    def control_case(self, out: str, **case) -> None:
        cases = json.loads(self.control.read_text())
        cases[out] = case
        self.control.write_text(json.dumps(cases), encoding="utf-8")

    def call(self, name: str, out: str, *, scenario: Scenario | None = None, **kwargs) -> dict:
        scenario = scenario or self.scenario
        kwargs.setdefault("timeout_s", self.calls[name]["timeout_s"] if name in self.calls else 50.0)
        kwargs.setdefault("ledger_root", scenario.root)
        kwargs.setdefault("operator_key_path", self.key_file)
        kwargs.setdefault("anchor_request", scenario.api)
        kwargs.setdefault("binary", self.fake)
        kwargs.setdefault("now", IN_WINDOW)
        return validate_call(name, self.root / out, **kwargs)

    def launched(self, out: str) -> bool:
        return (self.root / out / "argv0.txt").is_file()  # the fake solver's first act

    def run_together(self, requests: list[tuple]) -> dict:
        """validate-reference for each (scenario, call, out) at once, each in its own thread: out -> its receipt, or
        the exception it raised."""
        results = {}

        def run(scenario, call, out):
            try:
                results[out] = self.call(call, out, scenario=scenario)
            except Exception as exc:  # reported by the caller
                results[out] = exc
        threads = [threading.Thread(target=run, args=request) for request in requests]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(180)
        return results

    @staticmethod
    def popen_spy(on_spawn):
        """Every process validate-reference starts passes on_spawn(argv) first, then the real Popen."""
        def spy(argv, *args, **kwargs):
            on_spawn(list(argv))
            return mock.DEFAULT  # the wrapped, real Popen
        return mock.patch.object(reference_validation.subprocess, "Popen", wraps=subprocess.Popen, side_effect=spy)


class ManifestEntryTests(EntryCase):
    """validate-reference: the bootstrap path, bound to the frozen manifest and the operator's grant (astra #56794,
    #56837, #56858; warden #56967 P2-2)."""

    def test_anything_the_manifest_or_the_operator_does_not_allow_is_refused_before_dispatch(self):
        drifted = self.root / "drifted.json"
        manifest = json.loads(self.manifest_path.read_text())
        manifest["source"]["generator_sha256"]["sundai_tap/fastSA.py"] = "0" * 64
        drifted.write_bytes(slab049._dump(manifest))
        stranger = self.root / "stranger.pem"
        stranger.write_bytes(Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        garbled = self.root / "garbled.pem"
        garbled.write_text("not a key", encoding="utf-8")
        self.scenario.reserve(*self.calls)
        expired = self.grant("expired", api=self.scenario.api, window=("2026-10-01T00:00:00+00:00",
                                                                        "2026-10-02T00:00:00+00:00"))
        narrow = self.grant("narrow", api=self.scenario.api, calls=[R_ASCEND])
        greedy = self.grant("greedy", api=self.scenario.api, cap=700.0)
        unreserved = self.grant("unreserved", grant_id="g-unreserved")
        unreadable = self.grant("unreadable")
        unreadable.reserve(P_ASCEND)
        unreadable.api.down = {("GET", "/git/ref/")}
        empty = self.root / "empty-root"
        gate0_anchor.ledger_dir(empty, self.manifest_sha256).mkdir(parents=True)
        refusals = {
            "unlisted call": dict(name="u-hs6-ascend910-tap25d-fig6a-raw-g64"),
            "snapped identity": dict(name="p-hs6-ascend910-tap25d-fig6a-snapped-g64"),
            "deferred reference": dict(name=P_ASCEND, reference="ascend910-tap25d-fig6c"),
            "grid 128": dict(name=P_ASCEND, grid=128),
            "other engine": dict(name=P_ASCEND, kind="hotspot6_tap_faithful"),
            "no timeout": dict(name=P_ASCEND, timeout_s=None),
            "the old 60 s grid-64 timeout": dict(name=P_ASCEND, timeout_s=60.0),
            "a 50 s timeout on a 15 s row": dict(name=G32_ASCEND, timeout_s=50.0),
            "timeout 1e6": dict(name=P_ASCEND, timeout_s=1e6),
            "after the manifest window": dict(name=P_ASCEND, now=datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)),
            "the prior manifest": dict(name=P_ASCEND, manifest_path=REPO_ROOT / slab049.PRIOR_MANIFEST["path"]),
            "a drifted executed pin": dict(name=P_ASCEND, manifest_path=drifted),
            "no operator key": dict(name=P_ASCEND, operator_key_path=None),
            "another key": dict(name=P_ASCEND, operator_key_path=stranger),
            "an unreadable key": dict(name=P_ASCEND, operator_key_path=garbled),
            "no launch credential": dict(name=P_ASCEND, anchor_request=None),
            "no ledger root": dict(name=P_ASCEND, ledger_root=None),
            "no ledger": dict(name=P_ASCEND, ledger_root=self.root / "nowhere"),
            "a missing grant": dict(name=P_ASCEND, ledger_root=empty),
            "an expired grant window": dict(name=P_ASCEND, scenario=expired),
            "a call outside the grant": dict(name=P_ASCEND, scenario=narrow),
            "a grant cap above 600 CPU-s": dict(name=P_ASCEND, scenario=greedy),
            "no reserve tag": dict(name=P_ASCEND, scenario=unreserved),
            "unreadable tags": dict(name=P_ASCEND, scenario=unreadable),
        }
        stale = self.root / "stale-provenance"
        shutil.copy(self.fake, stale)
        self.write_provenance(stale)
        stale.write_text(stale.read_text() + "# rebuilt\n")
        guarded = self.root / "ci-guarded"  # what a CI_ALLOCATION=1 build compiles in (sundai_hotspot/ci_entry.h)
        guarded.write_bytes(self.fake.read_bytes() + b"# " + provenance.CI_ENTRY_GUARD + b"\n")
        guarded.chmod(0o755)
        self.write_provenance(guarded)
        with mock.patch("sundai_hotspot.reference_validation._run_call") as dispatch:  # reservation and launch
            for rule, arguments in refusals.items():
                with self.subTest(rule=rule), self.assertRaises(CallRefused):
                    name = arguments.pop("name")
                    self.call(name, f"out-{rule.replace(' ', '-')}", **arguments)
            with mock.patch("sundai_hotspot.reference_validation.platform.machine", return_value="aarch64"):
                with self.assertRaises(CallRefused):
                    self.call(P_ASCEND, "out-host")
            with self.assertRaisesRegex(CallRefused, "provenance"):
                self.call(P_ASCEND, "out-stale", binary=stale)
            with self.assertRaisesRegex(CallRefused, "CI entry guard"):
                self.call(P_ASCEND, "out-guarded", binary=guarded)
            dispatch.assert_not_called()
        self.assertEqual(len(self.scenario.ledger()["entries"]), 1, "a refused call is never reserved")
        self.assertEqual((self.scenario.api.admitted_calls(), self.scenario.api.launch_tags()), ([], []))

    def test_an_unpinned_manifest_admits_nothing_and_passes_nothing(self):
        # The committed manifest carries warden's pinned key (test_the_operator_key_is_pinned_...). The manifest
        # this tree generates without a key, as before the pin, still admits nothing and passes nothing.
        unpinned = self.root / "unpinned" / slab049.MANIFEST_NAME
        unpinned.parent.mkdir()
        with mock.patch.object(slab049, "OPERATOR_PUBLIC_KEY", None):
            unpinned.write_bytes(slab049._dump(slab049.build_call_list()))
            self.assertIsNone(json.loads(unpinned.read_text(encoding="utf-8"))["operator"]["public_key_ed25519"])
            with self.assertRaisesRegex(CallRefused, "no operator public key is pinned"):
                self.call(P_ASCEND, "unpinned", manifest_path=unpinned)
            with self.assertRaisesRegex(GateZeroRefusal, "no operator public key is pinned"):
                build_record("hotspot6", self.fake, ledger_root=self.scenario.root, tags=self.scenario.tags,
                             manifest_path=unpinned)

    def test_ci_allocation_refuses_before_anything_runs(self):
        """Main's CI allocation (SLAB-046): native HotSpot launches in CI go through ci_gate; SLAB-049 never solves there."""
        self.scenario.reserve(P_ASCEND)
        with mock.patch.dict(os.environ, {"CI_ALLOCATION": "1"}), \
                mock.patch("sundai_hotspot.reference_validation._run_call") as dispatch:
            with self.assertRaisesRegex(CallRefused, "never runs under CI allocation"):
                self.call(P_ASCEND, "ci")
            dispatch.assert_not_called()
        self.assertEqual(len(self.scenario.ledger()["entries"]), 1)
        self.assertFalse((self.root / "ci").exists())

    def test_bootstrap_receipts_need_no_pass_bind_every_field_and_unlock_search(self):
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", hotspot_binary=self.fake)
        peaks = {P_ASCEND: 75.30, R_ASCEND: 75.30, P_MICRO: 116.50, R_MICRO: 116.50}
        self.scenario.reserve(*peaks)
        for name, peak in peaks.items():
            self.control_case(name, peak_c=peak)
            receipt = self.call(name, name)
            self.assertEqual((receipt["status"], receipt["exit_status"]), ("exited", 0), receipt.get("error"))
            run = self.root / name
            self.assertEqual((run / "rlimit_cpu.txt").read_text(), "50 50")  # RLIMIT_CPU soft = hard = timeout
            on_disk = gate0_anchor.verify(self.public, json.loads((run / "receipt.json").read_text()))  # signed
            self.assertEqual((on_disk["call"], on_disk["manifest_sha256"], on_disk["grant_id"], on_disk["layout_identity"]),
                             (name, self.manifest_sha256, GRANT_ID, "raw"))
            self.assertEqual(on_disk["raw_layout_sha256"], gate_zero.reference(on_disk["reference"]).raw_layout_sha256)
            self.assertFalse(on_disk["geometry"]["search_lattice_checked"])
            self.assertEqual(on_disk["build_provenance"]["sha256"], _sha256(provenance.provenance_path(self.fake)))
            self.assertEqual(on_disk["runtime"], on_disk["runtime_after"])
            self.assertEqual(on_disk["claim"]["ref"], gate0_anchor.tag_ref(GRANT_ID, "launch", name))
            self.assertEqual(on_disk["admission"]["ref"],
                             gate0_anchor.admit_ref(GRANT_ID, list(peaks).index(name) + 1))
            executed = Path((run / "argv0.txt").read_text())
            self.assertEqual(executed.name, f"evaluator-{_sha256(self.fake)[:16]}")  # the private copy ran
            self.assertNotEqual(executed, self.fake.resolve())
            self.assertFalse(executed.parent.exists(), "the private copy is removed after the call")
            record = on_disk["solve_record"]
            self.assertEqual(record["config_sha256"], on_disk["inputs"]["new_hotspot.config"])
            for field in ("active_layer_grid_peak", "chiplet_centre_mapping", "historical_tap_stdout_selector",
                          "spreader_sink_hottest_cell_rises", "spreader_sink_drop_diagnostic",
                          "same_index_stack_at_active_argmax"):
                self.assertIn(field, record)
            self.assertNotIn("measured", json.dumps(on_disk))
            settlement = self.scenario.entries(name)["settlement"]
            self.assertEqual(settlement["receipt_sha256"], _sha256(run / "receipt.json"))
            self.assertGreater(settlement["charged_cpu_s"], 0.0)
            self.scenario.tag("settle", name, receipt["settle_tag_message"])  # the operator writes what was printed
        with self.assertRaises(CallRefused):  # each call runs once
            self.call(P_ASCEND, "again")
        result = self.record(self.scenario, self.fake)
        self.assertEqual(result["verdict"], "PASS", (result["failures"], result["missing"]))
        oracle = make_oracle("hotspot6", "search", hotspot_binary=self.fake, gate_zero_record=result,
                             ledger_root=self.scenario.root, tags=self.scenario.tags)
        self.assertIsNotNone(oracle.gate_zero)
        report = reference_validation.report(ledger_root=self.scenario.root, tags=self.scenario.tags)
        self.assertEqual(len(report["calls"]), 12)
        self.assertEqual(len(report["not_completed"]), 8)
        row = next(r for r in report["rows"] if r["kind"] == "hotspot6" and r["reference"] == ASCEND)
        self.assertTrue(row["replay_byte_identical"])
        self.assertEqual([layer["layer"] for layer in row["same_index_stack_g64"][0]["layers"]], [4, 5, 6, 7])

    def test_a_grid_32_row_runs_under_its_own_15_s_limit(self):
        name = call_id("primary", "hotspot6", MICRO, 32)
        self.scenario.reserve(name)
        receipt = self.call(name, name)
        self.assertEqual((receipt["status"], receipt["timeout_s"], receipt["cpu_limit_s"]), ("exited", 15.0, 15))
        self.assertEqual((self.root / name / "rlimit_cpu.txt").read_text(), "15 15")

    def test_the_anchored_aggregate_charges_every_admitted_call_its_full_envelope(self):
        """astra #57024, #57025: the full envelope is reserved at admission and never reclaimed."""
        small = self.grant("small", cap=80.0)
        small.reserve(P_ASCEND, G32_ASCEND)
        self.assertEqual(self.call(P_ASCEND, "first", scenario=small)["status"], "exited")  # 58.5 of 80
        with self.assertRaisesRegex(CallRefused, "would pass the grant's 80 CPU-s cap"):
            self.call(G32_ASCEND, "second", scenario=small)  # 58.5 + 23.5 > 80
        fresh = self.grant("fresh", api=small.api, cap=80.0)  # a fresh ledger reads the same admission chain
        with self.assertRaisesRegex(CallRefused, "would pass the grant's 80 CPU-s cap"):
            self.call(G32_ASCEND, "third", scenario=fresh)
        heavy = self.grant("heavy")  # a measured overshoot is charged in full
        heavy.fabricate({P_MICRO: 116.27}, charged_cpu_s=590.0)
        heavy.reserve(G32_ASCEND)
        with self.assertRaisesRegex(CallRefused, "590.00 CPU-s already charged"):
            self.call(G32_ASCEND, "overshoot", scenario=heavy)
        failed = self.grant("failed")  # failed or unknown work stays charged
        failed.fabricate({P_MICRO: 116.27, R_MICRO: 116.27}, settled={P_MICRO: ("setup_error", None)})
        self.assertEqual(self.charged(failed), 2 * 58.5)

    def test_the_wall_deadline_kills_the_whole_process_group(self):
        with mock.patch.dict(slab049.TIMING, {"grid64_timeout_s": 3.0}):  # time to start its child
            self.regenerate_manifest()
            short = self.grant("short")
            short.reserve(P_ASCEND)
            self.control_case("sleeper", sleep=True)
            started = time.monotonic()
            receipt = self.call(P_ASCEND, "sleeper", scenario=short, timeout_s=3.0)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("wall_timeout", None))
        child = int((self.root / "sleeper" / "child.pid").read_text())
        deadline = time.monotonic() + 5
        while not _process_gone(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(_process_gone(child), "the solver's descendant survived the group kill")
        self.assertEqual(short.entries(P_ASCEND)["settlement"]["status"], "wall_timeout")

    def test_rlimit_cpu_enforces_cpu_whatever_the_wall_deadline(self):
        """astra #56858: a wall timeout alone is not CPU enforcement; the per-process CPU limit kills by itself."""
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-c", "while True: pass"], start_new_session=True,
                                   **provenance.cpu_limited(1))
        try:
            self.assertEqual(process.wait(timeout=30), -signal.SIGKILL)
        finally:
            if process.poll() is None:  # the limit did not act: never leave the loop running
                process.kill()
                process.wait()
        self.assertLess(time.monotonic() - started, 30)

    def test_a_launch_failure_keeps_a_settled_receipt(self):
        unlaunchable = self.root / "not-executable"
        unlaunchable.write_bytes(FAKE_BINARIES["hotspot6"])
        self.write_provenance(unlaunchable)
        self.scenario.reserve(P_ASCEND)
        receipt = self.call(P_ASCEND, "launch", binary=unlaunchable)
        self.assertEqual(receipt["status"], "launch_error")
        on_disk = json.loads((self.root / "launch" / "receipt.json").read_text())
        self.assertEqual(on_disk["status"], "launch_error")
        self.assertIn("finished_utc", on_disk)
        self.assertEqual(self.scenario.entries(P_ASCEND)["settlement"]["status"], "launch_error")

    def test_every_post_reservation_failure_settles_in_the_ledger_and_is_never_retried(self):
        """astra (#56982 P2-2): a failure between admission and staging used to leave the reservation unsettled."""
        self.scenario.reserve(P_ASCEND, P_MICRO)
        (self.root / "blocker").write_text("a file where the output parent should be", encoding="utf-8")
        receipt = self.call(P_ASCEND, "blocker/run")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("setup_error", None))
        settlement = self.scenario.entries(P_ASCEND)["settlement"]
        self.assertEqual(settlement["status"], "setup_error")
        self.assertIsNone(settlement["receipt_sha256"])  # no receipt could be written, the ledger still settles
        self.assertTrue(settlement["receipt_error"])
        self.assertFalse(self.scenario.api.has("launch", P_ASCEND))  # it never reached its claim
        with self.assertRaisesRegex(CallRefused, "already in the ledger"):  # and is never retried
            self.call(P_ASCEND, "elsewhere")
        real, writes = reference_validation._write_durably, []

        def first_write_fails(path, data):
            writes.append(path)
            if len(writes) == 1:
                raise OSError(28, "No space left on device")
            return real(path, data)
        with mock.patch.object(reference_validation, "_write_durably", side_effect=first_write_fails):
            receipt = self.call(P_MICRO, "first-write")
        self.assertEqual(receipt["status"], "setup_error")
        settlement = self.scenario.entries(P_MICRO)["settlement"]
        self.assertEqual(settlement["status"], "setup_error")
        self.assertIn("No space left on device", settlement["error"])
        self.assertEqual(settlement["receipt_sha256"], _sha256(self.root / "first-write" / "receipt.json"))
        self.assertEqual(self.charged(self.scenario), 2 * 58.5)  # both stay charged their full envelopes

    def test_a_truncated_grid_after_exit_zero_keeps_the_raw_outputs_and_is_incomplete(self):
        self.scenario.reserve(P_ASCEND)
        self.control_case("truncated", truncate=True)
        receipt = self.call(P_ASCEND, "truncated")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("record_error", 0))
        self.assertIn("GridFormatError", receipt["error"])
        self.assertEqual(set(receipt["outputs"]), set(gate_zero.RECEIPT_OUTPUTS))
        self.scenario.tag("settle", P_ASCEND, receipt["settle_tag_message"])
        record = self.record(self.scenario, self.fake)
        self.assertEqual(record["verdict"], "INCOMPLETE")
        self.assertIn("record_error", next(m["reason"] for m in record["missing"] if m["call"] == P_ASCEND))


class ClaimTests(EntryCase):
    """astra #57031: the atomic launch claim, through the real entrypoint with the create-only fake API. The order of
    one call is admission, setup, the precheck, staging, claim, launch; only a successful create launches."""

    def solver_popen(self, before_launch):
        """A spy on the solver's launch (the TAP argv): before_launch runs first, then the real Popen."""
        return self.popen_spy(lambda argv: before_launch() if "-steady_file" in argv else None)

    def test_admission_staging_claim_launch_in_that_order(self):
        self.scenario.reserve(P_ASCEND)
        events, spawned, out = [], [], self.root / "order"

        def staged():
            return sorted(path.name for path in out.iterdir()) if out.exists() else []

        def at_create(ref):
            if "/admit-" in ref:
                events.append(("admission", len(spawned), staged()))
            elif "/launch-" in ref:
                events.append(("claim", "reservation" in self.scenario.entries(P_ASCEND), staged()))

        def on_spawn(argv):
            spawned.append(argv)
            if "-steady_file" in argv:
                events.append(("launch", self.scenario.api.has("launch", P_ASCEND), staged()))
        self.scenario.api.before_create = at_create
        with self.popen_spy(on_spawn):
            receipt = self.call(P_ASCEND, "order")
        self.assertEqual(receipt["status"], "exited")
        self.assertEqual([event[0] for event in events], ["admission", "claim", "launch"])
        (_, processes, at_admission), (_, reserved, at_claim), (_, claimed, at_launch) = events
        self.assertEqual((processes, at_admission), (0, []))  # admitted before any process and any file
        self.assertTrue(reserved)  # the signed reservation, then setup and staging
        self.assertLessEqual({"receipt.json", *slab049.REFERENCE_INPUTS}, set(at_claim))
        self.assertTrue(claimed)   # then the claim, before the launch
        self.assertEqual(set(at_launch) - set(at_claim), {"stdout.txt", "stderr.txt"})  # nothing in between

    def test_a_sequential_pair_launches_exactly_once(self):
        self.scenario.reserve(P_ASCEND)
        self.assertEqual(self.call(P_ASCEND, "first")["status"], "exited")
        fresh = self.grant("ledger-b", api=self.scenario.api)  # the operator's second ledger for the same grant
        for scenario, out, reason in ((self.scenario, "again", "already in the ledger"),
                                      (fresh, "elsewhere", "already admitted")):
            with self.subTest(ledger=out), self.assertRaisesRegex(CallRefused, reason):
                self.call(P_ASCEND, out, scenario=scenario)
        self.assertEqual(self.scenario.api.launch_tags(), [self.scenario.api.ref("launch", P_ASCEND)])
        self.assertEqual([self.launched(out) for out in ("first", "again", "elsewhere")], [True, False, False])

    def test_a_concurrent_pair_launches_exactly_once(self):
        """Two requests for one call on two ledgers at once: the anchored admission takes exactly one before either
        does any process work; the other is refused and spends nothing."""
        self.scenario.reserve(P_ASCEND)
        other = self.grant("ledger-b", api=self.scenario.api)
        rendezvous = threading.Barrier(2)

        def meet(path):  # both requests read the admission chain before either takes a place in it
            if "/admit-" in path:
                with contextlib.suppress(threading.BrokenBarrierError):
                    rendezvous.wait(timeout=5)
        self.scenario.api.before_read = meet
        results = self.run_together([(self.scenario, P_ASCEND, "a"), (other, P_ASCEND, "b")])
        self.scenario.api.before_read = None
        receipts = {out: r for out, r in results.items() if isinstance(r, dict)}
        refusals = {out: r for out, r in results.items() if isinstance(r, CallRefused)}
        self.assertEqual((len(receipts), len(refusals)), (1, 1), results)
        self.assertEqual(next(iter(receipts.values()))["status"], "exited")
        self.assertRegex(str(next(iter(refusals.values()))), "taken by another request|already admitted")
        self.assertEqual(sum(self.launched(out) for out in ("a", "b")), 1)
        loser = next(iter(refusals))
        self.assertEqual(len((other if loser == "b" else self.scenario).ledger()["entries"]), 1)  # nothing spent
        self.assertEqual(self.scenario.api.admitted_calls(), [P_ASCEND])

    def test_a_launch_ref_taken_first_by_another_request_refuses_the_launch(self):
        """The claim's create is the atomic step at launch: when the launch ref appears first (another request
        holding it), the create fails and nothing launches."""
        self.scenario.reserve(P_ASCEND)

        def rival(ref):
            if "/launch-" in ref:
                with self.scenario.api.lock:
                    self.scenario.api.refs.setdefault(ref, "0" * 40)
        self.scenario.api.before_create = rival
        receipt = self.call(P_ASCEND, "raced")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("claim_refused", None))
        self.assertFalse(self.launched("raced"))
        self.assertEqual(self.scenario.entries(P_ASCEND)["settlement"]["status"], "claim_refused")

    def test_a_deleted_or_rolled_back_reservation_never_readmits_a_call(self):
        """warden #56967 P2-2: deleting a reservation would readmit its call without the anchor."""
        self.scenario.reserve(P_ASCEND, P_MICRO)
        self.assertEqual(self.call(P_ASCEND, "ran")["status"], "exited")
        self.assertEqual(self.call(P_MICRO, "ran-too")["status"], "exited")
        entries = sorted(self.scenario.dir.glob("*.json"))  # grant, then P_ASCEND's and P_MICRO's two entries
        entries[1].unlink()  # P_ASCEND's reservation, from the middle of the chain
        with self.assertRaisesRegex(CallRefused, "contiguous"):
            self.call(P_ASCEND, "after-deletion")
        for entry in entries[2:]:  # the rest too: a valid prefix holding only the grant
            entry.unlink()
        for name in (P_ASCEND, P_MICRO):
            with self.subTest(call=name), self.assertRaisesRegex(CallRefused, "already admitted"):
                self.call(name, f"after-rollback-{name}")
        self.assertFalse(any(self.launched(out) for out in ("after-deletion", f"after-rollback-{P_ASCEND}",
                                                             f"after-rollback-{P_MICRO}")))

    def test_a_crash_after_the_claim_is_never_retried(self):
        self.scenario.reserve(P_ASCEND)

        def die():
            raise SystemExit("validate-reference killed between its claim and the launch")
        with self.solver_popen(die), mock.patch.object(reference_validation, "_settle"):  # dead: nothing settles
            with self.assertRaises(SystemExit):
                self.call(P_ASCEND, "crashed")
        self.assertTrue(self.scenario.api.has("launch", P_ASCEND))
        self.assertFalse(self.scenario.api.has("settle", P_ASCEND))
        self.assertEqual(set(self.scenario.entries(P_ASCEND)), {"reservation"})
        fresh = self.grant("ledger-b", api=self.scenario.api)
        for scenario, out, reason in ((self.scenario, "retry", "already in the ledger"),
                                      (fresh, "retry-b", "already admitted")):
            with self.subTest(ledger=out), self.assertRaisesRegex(CallRefused, reason):
                self.call(P_ASCEND, out, scenario=scenario)  # never from the absence of a settle tag
        self.assertFalse(any(self.launched(out) for out in ("crashed", "retry", "retry-b")))
        self.assertIn(P_ASCEND, [m["call"] for m in self.record(self.scenario, self.fake)["missing"]])

    def test_an_uncertain_create_launches_nothing_and_is_never_retried(self):
        for label, mode in (("lost-after-create", "after"), ("failed-before-create", "before")):
            with self.subTest(create=label):
                scenario = self.grant(label)
                scenario.reserve(P_ASCEND)
                scenario.api.fail_create = {"/launch-": mode}
                receipt = self.call(P_ASCEND, label + "-run", scenario=scenario)
                self.assertEqual((receipt["status"], receipt["exit_status"]), ("claim_uncertain", None))
                self.assertFalse(self.launched(label + "-run"))
                self.assertEqual(scenario.entries(P_ASCEND)["settlement"]["status"], "claim_uncertain")
                scenario.api.fail_create = {}
                with self.assertRaises(CallRefused):  # consumed in its ledger
                    self.call(P_ASCEND, label + "-again", scenario=scenario)
                scenario.tag("settle", P_ASCEND, receipt["settle_tag_message"])  # the operator reconciles it
                fresh = self.grant(label + "-b", api=scenario.api)
                with self.assertRaises(CallRefused):  # and no fresh ledger can relaunch it
                    self.call(P_ASCEND, label + "-b-run", scenario=fresh)
                self.assertFalse(self.launched(label + "-b-run"))

    def test_no_credential_means_no_launch(self):
        self.scenario.reserve(P_ASCEND)
        with self.assertRaisesRegex(CallRefused, "no launch credential"):
            self.call(P_ASCEND, "no-credential", anchor_request=None)
        stderr = io.StringIO()
        with mock.patch.object(reference_validation, "_now", return_value=IN_WINDOW), \
                contextlib.redirect_stderr(stderr):
            code = reference_validation.main(["validate-reference", "--call", P_ASCEND, "--timeout", "50",
                                              "--out", str(self.root / "cli"), "--ledger-root", str(self.scenario.root),
                                              "--operator-key", str(self.key_file)])
        self.assertEqual(code, 2)
        self.assertIn("no launch credential (SLAB049_ANCHOR_TOKEN)", stderr.getvalue())
        self.assertFalse(self.launched("no-credential") or self.launched("cli"))
        self.assertEqual((len(self.scenario.ledger()["entries"]), self.scenario.api.admitted_calls(),
                          self.scenario.api.launch_tags()), (1, [], []))


class AccountingTests(EntryCase):
    """root's round-D review of PR #56 (P2): accounting starts before any work, and every process an invocation
    starts belongs to an admitted, anchored attempt that settles and is charged. Each started process counts as one
    work unit here; these are units and markers, not measured CPU."""

    def setUp(self):
        super().setUp()
        # The fake solver is a script, which no loader lists. A stand-in loader (/bin/true's own listing, a real
        # process) makes the precheck do process work, as the loader does for HotSpot.
        self.patch(provenance, "elf_interpreter", lambda data: "/bin/true")
        self.write_provenance(self.fake)
        self.mismatched = self.root / "mismatched-libraries"
        shutil.copy(self.fake, self.mismatched)
        claimed = provenance.build_provenance("hotspot6", self.mismatched)
        claimed["libraries"] = {"dynamic": True, "libraries": [
            {"name": "libblas.so.3", "path": "/x", "realpath": "/x", "sha256": "0" * 64}]}
        provenance.provenance_path(self.mismatched).write_text(json.dumps(claimed), encoding="utf-8")

    def test_every_unit_of_work_belongs_to_an_admitted_attempt_and_is_charged(self):
        """root's witness: 10 units of child work of which the old order charged 9, and library-mismatch refusals
        with no ledger entry or anchored charge. Here: two calls that run (4 units each: the precheck's listing, the
        generator, the solver, the listing after the run) and two library-mismatch refusals (1 unit each)."""
        runs, refusals = (P_ASCEND, P_MICRO), (R_ASCEND, R_MICRO)
        self.scenario.reserve(*runs, *refusals)
        units, current = [], {}

        def on_spawn(argv):
            call = current["call"]
            kind = ("listing" if argv[0] == "/bin/true" else "solver" if "-steady_file" in argv
                    else "generator" if argv[:2] == [sys.executable, "-c"] else "other")
            units.append((call, kind, call in self.scenario.api.admitted_calls()
                          and "reservation" in self.scenario.entries(call)))
        with self.popen_spy(on_spawn):
            for name in runs:
                current["call"] = name
                self.assertEqual(self.call(name, name)["status"], "exited")
            for name in refusals:
                current["call"] = name
                receipt = self.call(name, name, binary=self.mismatched)
                self.assertEqual((receipt["status"], receipt["exit_status"]), ("runtime_refused", None))
        self.assertEqual(len(units), 10, units)
        self.assertEqual([unit for unit in units if not unit[2]], [])  # all 10 inside an admitted, anchored attempt
        self.assertEqual({name: [kind for call, kind, _ in units if call == name] for name in runs + refusals},
                         {**{name: ["listing", "generator", "solver", "listing"] for name in runs},
                          **{name: ["listing"] for name in refusals}})
        for name in refusals:  # each refusal is in the ledger and the admission chain, settled and charged
            settlement = self.scenario.entries(name)["settlement"]
            self.assertEqual(settlement["status"], "runtime_refused")
            self.assertGreater(settlement["charged_cpu_s"], 0.0)
            self.assertFalse((self.root / name / "sample.steady").exists())  # refused before staging
        self.assertEqual(sorted(self.scenario.api.admitted_calls()), sorted(runs + refusals))
        self.assertEqual(self.charged(self.scenario), 4 * 58.5)

    def test_a_receipt_charges_the_first_check(self):
        """The accounting starts before the first process-capable check, so a receipt charges it: 0.3 CPU-s of
        parent work injected at the first listing appears in the receipt and its settlement."""
        self.scenario.reserve(P_ASCEND)
        seen = []

        def on_spawn(argv):
            if argv[0] == "/bin/true" and not seen:
                seen.append({"self_s": reference_validation._self_cpu_s(),
                             "children_s": reference_validation._children_cpu_s()})
                end = time.process_time() + 0.3
                while time.process_time() < end:  # injected work at the first check
                    pass
        with self.popen_spy(on_spawn):
            receipt = self.call(P_ASCEND, "first-check")
        self.assertEqual(receipt["status"], "exited")
        self.assertEqual(receipt["runtime"]["loader"], "/bin/true")  # the first check is in the receipt
        baseline = receipt["cpu_baseline"]
        self.assertLessEqual(baseline["self_s"], seen[0]["self_s"])  # the accounting started before it
        self.assertLessEqual(baseline["children_s"], seen[0]["children_s"])
        self.assertGreaterEqual(receipt["self_cpu_s"], 0.3)  # and charges it
        settlement = self.scenario.entries(P_ASCEND)["settlement"]
        self.assertEqual((settlement["cpu_baseline"], settlement["charged_cpu_s"]), (baseline, receipt["charged_cpu_s"]))


class AdmissionTests(EntryCase):
    """root's round-D review of PR #56 (P2): the grant's balance is checked and the reservation appended atomically,
    and the admission is anchored, so concurrency, a second ledger or a ledger rollback can never pass the cap or
    readmit a call."""

    def test_two_requests_cannot_both_spend_the_last_of_the_balance(self):
        """root's witness: 490 charged under a 600 cap; two distinct 58.5 requests at once used to leave 607."""
        for label, shared in (("one ledger", True), ("two ledgers", False)):
            with self.subTest(label):
                first = self.grant(label.replace(" ", "-") + "-a")
                second = first if shared else self.grant(label.replace(" ", "-") + "-b", api=first.api)
                first.fabricate({P_ASCEND: 75.09}, charged_cpu_s=490.0)
                self.assertEqual(self.charged(first), 490.0)
                first.reserve(P_MICRO, R_MICRO)
                rendezvous = threading.Barrier(2)

                def meet(path):  # both requests read the balance at once whenever the code lets them
                    if "/admit-" in path:
                        with contextlib.suppress(threading.BrokenBarrierError):
                            rendezvous.wait(timeout=2)
                first.api.before_read = meet
                prefix = label.replace(" ", "-")
                results = self.run_together([(first, P_MICRO, prefix + "-p"), (second, R_MICRO, prefix + "-r")])
                first.api.before_read = None
                ran = [r for r in results.values() if isinstance(r, dict)]
                refused = [r for r in results.values() if isinstance(r, CallRefused)]
                self.assertEqual((len(ran), len(refused)), (1, 1), results)
                self.assertEqual(ran[0]["status"], "exited")
                self.assertRegex(str(refused[0]), "would pass the grant's 600 CPU-s cap|taken by another request")
                self.assertEqual(len(first.api.admitted_calls()), 2)
                for scenario in (first, second):
                    self.assertEqual(self.charged(scenario), 490.0 + 58.5)  # within 600, the same on every ledger

    def test_an_admitted_call_is_never_readmitted_even_after_a_rollback_before_its_claim(self):
        """The admission is anchored before any process work, so the work before the launch claim is never free: a
        crash after admission and a ledger rolled back to its grant cannot readmit the call, here or elsewhere."""
        self.scenario.reserve(P_ASCEND)

        def crash(*args, **kwargs):
            raise SystemExit("validate-reference killed after its admission, before its claim")
        with mock.patch.object(gate0_anchor, "claim_launch", side_effect=crash), \
                mock.patch.object(reference_validation, "_settle"):  # dead: nothing settles
            with self.assertRaises(SystemExit):
                self.call(P_ASCEND, "admitted-then-killed")
        self.assertEqual((self.scenario.api.admitted_calls(), self.scenario.api.launch_tags()), ([P_ASCEND], []))
        for entry in sorted(self.scenario.dir.glob("*.json"))[1:]:  # roll the ledger back to its grant
            entry.unlink()
        fresh = self.grant("ledger-b", api=self.scenario.api)
        for scenario, out in ((self.scenario, "readmit"), (fresh, "readmit-b")):
            with self.subTest(ledger=out), self.assertRaisesRegex(CallRefused, "already admitted"):
                self.call(P_ASCEND, out, scenario=scenario)
        self.assertEqual(self.charged(self.scenario), 58.5)  # its envelope stays charged
        self.assertFalse(any(self.launched(out) for out in ("admitted-then-killed", "readmit", "readmit-b")))

    def test_the_window_is_rechecked_at_the_final_admission_boundary(self):
        self.scenario.reserve(P_ASCEND)
        closed = datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)
        with mock.patch.object(reference_validation, "_now", return_value=IN_WINDOW), \
                mock.patch.object(gate0_anchor, "_now", return_value=closed):
            with self.assertRaisesRegex(CallRefused, "outside the window at admission"):
                self.call(P_ASCEND, "late", now=None)
        self.assertEqual((len(self.scenario.ledger()["entries"]), self.scenario.api.admitted_calls()), (1, []))

    def fake_clock(self) -> dict:
        """A clock half a minute before the cutoff (the grant's and the manifest's, 2026-11-01T12:00Z), read by
        validate-reference and the admission alike, and a stand-in loader so that the precheck would start a process
        if it were ever reached."""
        self.patch(provenance, "elf_interpreter", lambda data: "/bin/true")
        self.write_provenance(self.fake)
        clock = {"now": datetime(2026, 11, 1, 11, 59, 30, tzinfo=timezone.utc)}
        self.patch(reference_validation, "_now", lambda: clock["now"])
        self.patch(gate0_anchor, "_now", lambda: clock["now"])
        return clock

    def test_a_cutoff_crossed_during_the_remote_reads_admits_nothing(self):
        """root (#57263): the clock advances past the cutoff while the admission reads the anchor."""
        self.scenario.reserve(P_ASCEND)
        clock = self.fake_clock()

        def slow_read(path):
            if "/admit-" in path:
                clock["now"] = datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)
        self.scenario.api.before_read = slow_read
        spawned = []
        with self.popen_spy(spawned.append):
            with self.assertRaisesRegex(CallRefused, "outside the window at admission"):
                self.call(P_ASCEND, "late-read", now=None)
        self.assertEqual(spawned, [])  # no process started
        self.assertEqual((self.scenario.api.admitted_calls(), len(self.scenario.ledger()["entries"])), ([], 1))
        self.assertFalse((self.root / "late-read").exists())

    def test_a_create_that_returns_after_the_cutoff_stays_charged_and_runs_nothing(self):
        """root (#57263): the clock advances past the cutoff during the admission tag's CREATE."""
        self.scenario.reserve(P_ASCEND)
        clock = self.fake_clock()

        def slow_create(ref):
            if "/admit-" in ref:
                clock["now"] = datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)
        self.scenario.api.before_create = slow_create
        spawned = []
        with self.popen_spy(spawned.append):
            receipt = self.call(P_ASCEND, "late-create", now=None)
        self.assertEqual(spawned, [])  # no loader listing, no generator, no solver
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("window_closed", None))
        self.assertTrue(receipt["admission"]["late"])
        entries = self.scenario.entries(P_ASCEND)
        self.assertTrue(entries["reservation"]["admission"]["late"])  # the admission is retained
        self.assertEqual(entries["settlement"]["status"], "window_closed")
        self.assertGreater(entries["settlement"]["charged_cpu_s"], 0.0)
        self.assertEqual(self.scenario.api.admitted_calls(), [P_ASCEND])
        self.assertEqual(self.charged(self.scenario), 58.5)  # and charged its full envelope
        self.assertFalse(self.launched("late-create"))
        clock["now"] = datetime(2026, 11, 1, 11, 59, 30, tzinfo=timezone.utc)  # back in the window: still never again
        with self.assertRaisesRegex(CallRefused, "already in the ledger"):
            self.call(P_ASCEND, "late-create-again", now=None)

    def test_an_uncertain_or_forged_admission_runs_nothing(self):
        for label, mode in (("lost-after-create", "after"), ("failed-before-create", "before")):
            with self.subTest(create=label):
                scenario = self.grant(label)
                scenario.reserve(P_ASCEND)
                scenario.api.fail_create = {"/admit-": mode}
                with self.assertRaisesRegex(CallRefused, "outcome is unknown"):
                    self.call(P_ASCEND, label + "-run", scenario=scenario)
                scenario.api.fail_create = {}
                self.assertEqual(len(scenario.ledger()["entries"]), 1)
                self.assertFalse(self.launched(label + "-run"))
                if mode == "after":  # the tag exists: consumed and charged, never readmitted
                    self.assertEqual((scenario.api.admitted_calls(), self.charged(scenario)), ([P_ASCEND], 58.5))
                    with self.assertRaisesRegex(CallRefused, "already admitted"):
                        self.call(P_ASCEND, label + "-again", scenario=scenario)
                else:  # nothing was created: a later request may still admit it
                    self.assertEqual(scenario.api.admitted_calls(), [])
                    self.assertEqual(self.call(P_ASCEND, label + "-again", scenario=scenario)["status"], "exited")
        valid = {"call": P_MICRO, "envelope_cpu_s": 58.5, "total_cpu_s": 58.5, "previous_sha": None}
        forged = {"another envelope": [dict(valid, envelope_cpu_s=1.0, total_cpu_s=1.0)],
                  "a broken total": [dict(valid, total_cpu_s=1.0)],
                  "a broken link": [dict(valid, previous_sha="f" * 40)],
                  "a call outside the grant": [valid],
                  "a call admitted twice": [valid, dict(valid, total_cpu_s=117.0, previous_sha="@")]}
        for label, places in forged.items():
            with self.subTest(chain=label):
                outside = label == "a call outside the grant"
                scenario = self.grant(label.replace(" ", "-"), calls=[P_ASCEND] if outside else None)
                scenario.reserve(P_ASCEND)
                previous = None
                for seq, place in enumerate(places, start=1):  # written by someone holding the tag credential
                    fields = dict(place, previous_sha=previous if place["previous_sha"] == "@" else place["previous_sha"])
                    message = gate0_anchor.admit_message(GRANT_ID, self.manifest_sha256, seq, fields.pop("call"),
                                                         **fields)
                    commit = scenario.api("POST", "/git/commits", {"message": message, "tree": EMPTY_TREE,
                                                                   "parents": []})
                    scenario.api("POST", "/git/refs", {"ref": scenario.api.admit_ref(seq), "sha": commit["sha"]})
                    previous = commit["sha"]
                with self.assertRaisesRegex(CallRefused, "breaks the grant's admission chain"):
                    self.call(P_ASCEND, label.replace(" ", "-") + "-run", scenario=scenario)
                self.assertEqual(len(scenario.ledger()["entries"]), 1)


@unittest.skipUnless(os.name == "posix", "RLIMIT_CPU is POSIX")
class ChildLimitTests(unittest.TestCase):
    """warden #56967 P2-3: every child SLAB-049 starts has RLIMIT_CPU and a wall deadline. The solver's, the
    generator's (ExecutedSetTests) and the loader's (RuntimeLibraryTests) are checked on real processes; the
    analytic harness's gcc and run calls here."""

    def test_the_assembly_harness_compiles_and_runs_under_rlimit_cpu_and_a_wall_deadline(self):
        done, failed = subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 1, "", "no")
        with mock.patch.object(slab049.subprocess, "run", return_value=done) as run, \
                mock.patch.object(provenance, "cpu_limited", wraps=provenance.cpu_limited) as limited:
            slab049._run(["gcc", "-c", "x.c"], Path("."))
        self.assertEqual(run.call_args.kwargs["timeout"], slab049.COMPILE_TIMEOUT_S)
        self.assertIn("preexec_fn", run.call_args.kwargs)
        limited.assert_called_once_with(slab049.COMPILE_CPU_LIMIT_S)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(slab049.subprocess, "run", return_value=failed) as run, \
                mock.patch.object(provenance, "cpu_limited", wraps=provenance.cpu_limited) as limited:
            with self.assertRaises(RuntimeError):
                slab049.AssemblyHarness.run(Path(directory) / "harness", Path(directory), "c", "l", 16, 0.1)
        self.assertEqual(run.call_args.kwargs["timeout"], slab049.HARNESS_TIMEOUT_S)
        self.assertIn("preexec_fn", run.call_args.kwargs)
        limited.assert_called_once_with(slab049.HARNESS_CPU_LIMIT_S)


@unittest.skipUnless(os.name == "posix" and Path("/bin/true").is_file(), "a POSIX host with /bin/true")
class RuntimeLibraryTests(unittest.TestCase):
    """The loader listing: the binary's own PT_INTERP, under RLIMIT_CPU and a wall deadline; the program never runs."""

    @staticmethod
    def elf(interpreter: bytes | None) -> bytes:
        """A minimal little-endian ELF64 header with one program header: PT_INTERP, or PT_LOAD when there is none."""
        header = bytearray(64 + 56)
        header[:6] = b"\x7fELF\x02\x01"
        header[32:40] = (64).to_bytes(8, "little")      # e_phoff
        header[54:56] = (56).to_bytes(2, "little")      # e_phentsize
        header[56:58] = (1).to_bytes(2, "little")       # e_phnum
        header[64:68] = (3 if interpreter else 1).to_bytes(4, "little")
        if interpreter:
            header[72:80] = len(header).to_bytes(8, "little")              # p_offset
            header[96:104] = (len(interpreter) + 1).to_bytes(8, "little")  # p_filesz
            return bytes(header) + interpreter + b"\0"
        return bytes(header)

    def test_the_interpreter_is_read_from_the_elf_program_headers(self):
        self.assertEqual(provenance.elf_interpreter(self.elf(b"/lib/ld-test.so.1")), "/lib/ld-test.so.1")
        self.assertIsNone(provenance.elf_interpreter(self.elf(None)))
        for bad in (b"#!/bin/sh\n", self.elf(b"/lib/ld-test.so.1")[:70], b"\x7fELF\x03\x01" + bytes(64)):
            with self.assertRaises(ValueError):
                provenance.elf_interpreter(bad)
        self.assertTrue(provenance.elf_interpreter(Path("/bin/true").resolve().read_bytes()).startswith("/"))

    def test_libraries_are_resolved_with_hashes_without_running_the_program(self):
        resolved = provenance.resolved_libraries(Path("/bin/true"))
        self.assertTrue(resolved["dynamic"])
        self.assertEqual(resolved["loader"], provenance.elf_interpreter(Path("/bin/true").resolve().read_bytes()))
        libc = next(item for item in resolved["libraries"] if item["name"].startswith("libc.so"))
        self.assertEqual(libc["sha256"], _sha256(libc["realpath"]))
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "script"
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
            self.assertEqual(provenance.library_identity(provenance.resolved_libraries(script)), [])
            static = Path(directory) / "static"
            static.write_bytes(self.elf(None))
            self.assertEqual(provenance.resolved_libraries(static)["dynamic"], False)

    def test_the_listing_is_one_process_under_rlimit_cpu_killed_at_its_wall_deadline(self):
        loader = provenance.elf_interpreter(Path("/bin/true").resolve().read_bytes())
        with mock.patch.object(provenance.subprocess, "Popen", wraps=subprocess.Popen) as spawn, \
                mock.patch.object(provenance, "cpu_limited", wraps=provenance.cpu_limited) as limited:
            provenance.resolved_libraries(Path("/bin/true"))
        (argv,), options = spawn.call_args
        self.assertEqual((spawn.call_count, argv), (1, [loader, "/bin/true"]))
        self.assertTrue(options["start_new_session"])
        self.assertEqual(options["env"]["LD_TRACE_LOADED_OBJECTS"], "1")
        limited.assert_called_once_with(provenance.LOADER_CPU_LIMIT_S)
        self.assertIn("preexec_fn", options)  # RLIMIT_CPU is set in the child before exec
        with tempfile.TemporaryDirectory() as directory:
            never = Path(directory) / "never-written"
            os.mkfifo(never)  # the loader blocks opening it: a listing that never answers
            started = time.monotonic()
            with mock.patch.object(provenance, "LOADER_TIMEOUT_S", 0.5):
                self.assertEqual(provenance._loader_listing(loader, never),
                                 (None, "the loader passed its 0.5 s deadline"))
            self.assertLess(time.monotonic() - started, 30)

    def test_packages_and_owners_are_read_in_process_from_dpkgs_database(self):
        with tempfile.TemporaryDirectory() as directory:
            admin = Path(directory)
            (admin / "info").mkdir()
            (admin / "status").write_text(
                "Package: libsuperlu7\nStatus: install ok installed\nVersion: 7.0.1\n\n"
                "Package: libblas3\nStatus: deinstall ok config-files\nVersion: 3.12\n\n"
                "Package: unrelated\nStatus: install ok installed\nVersion: 1\n", encoding="utf-8")
            (admin / "info" / "libc6:amd64.list").write_text("/usr/lib/x86_64-linux-gnu/libc.so.6\n", encoding="utf-8")
            self.assertEqual(provenance._packages(admin), {"libsuperlu7": "7.0.1"})
            self.assertEqual(provenance._owners(["/usr/lib/x86_64-linux-gnu/libc.so.6", "/nowhere"], admin),
                             {"/usr/lib/x86_64-linux-gnu/libc.so.6": "libc6"})
            self.assertEqual(provenance._packages(admin / "absent"), {})


class VendoredHotSpot6Tests(unittest.TestCase):
    def test_vendored_files_are_the_upstream_blobs(self):
        self.assertEqual((HS6_ROOT / "UPSTREAM_COMMIT").read_text(encoding="ascii").strip(), gate_zero.HOTSPOT6_COMMIT)
        listed = dict(reversed(line.split()) for line in (HS6_ROOT / "UPSTREAM_BLOBS.txt").read_text(encoding="ascii").splitlines())
        vendored = {p.name for p in HS6_ROOT.iterdir() if p.is_file() and p.suffix not in (".o", ".d", ".a")
                    and p.name not in ("hotspot", "hotspot-tap-faithful", "hotfloorplan")
                    and not p.name.endswith(".provenance.json")}
        self.assertEqual(set(listed), vendored - {"UPSTREAM_COMMIT", "UPSTREAM_BLOBS.txt"})
        for name, blob in listed.items():
            data = (HS6_ROOT / name).read_bytes()
            if name == "temperature_grid.c":  # the writer-only SentiLab block, off by default
                data = strip_variant_blocks(data.decode("latin-1"), "SENTILAB_GRID_DUMP_ALL_LAYERS").encode("latin-1")
            self.assertEqual(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), blob, name)
        self.assertIn("NEITHER THE NAME OF ANY VIRGINIA ENTITY", (HS6_ROOT / "LICENSE").read_text(encoding="ascii"))

    def test_the_sentilab_block_touches_only_the_grid_writer(self):
        source = (HS6_ROOT / "temperature_grid.c").read_text(encoding="latin-1")
        self.assertEqual(source.count("#if SENTILAB_GRID_DUMP_ALL_LAYERS"), 2)
        self.assertIn(HOTSPOT6_TAG.decode("ascii"), source)
        block = source[source.index("#if SENTILAB_GRID_DUMP_ALL_LAYERS"):source.index("#endif", source.index("#if SENTILAB"))]
        for physics in ("find_res_3D", "rz", "getr", "dgssv", "steady_state"):
            self.assertNotIn(physics, block)

    def test_hotspot6_couples_layers_through_the_upper_layer_rz(self):
        source = (HS6_ROOT / "temperature_grid.c").read_text(encoding="latin-1")
        self.assertIn("define BC_det3D(l,n,i,j,nl,nr,nc)\t\t((n < nl-1) ? (1.0/find_res_3D(n, i, j, model,3)) : 0.0)",
                      source)
        self.assertIn("if(l < nl-1) Rb = find_res_3D(l,i,j,model,3);", source)
        self.assertNotIn("double find_res(", source)

    def test_build_script_covers_both_architectures_both_binaries_and_their_provenance(self):
        script = (REPO_ROOT / "scripts" / "build_hotspot6.sh").read_text(encoding="utf-8")
        for needle in ("x86_64|aarch64)", "SUPERLU=0", "SUPERLU=1", "-DSENTILAB_GRID_DUMP_ALL_LAYERS=1",
                       "-ffp-contract=off", "hotspot-tap-faithful", "sha256sum",
                       "python3 -m sundai_hotspot.provenance hotspot6 hotspot6_tap_faithful",
                       "it does not make results bit-identical across architectures"):
            self.assertIn(needle, script)
        self.assertIn("python3 -m sundai_hotspot.provenance hotspot7_default",
                      (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8"))


class KnownAnswerSlabTests(unittest.TestCase):
    """The analytic slab fixture: declared now, run later under its own 2-call allocation."""

    def test_expected_rises_follow_the_series_resistance(self):
        hs6, hs7 = slab049.known_answer_expected("hotspot6"), slab049.known_answer_expected("hotspot7_default")
        self.assertAlmostEqual(hs6["expected_rise_K"], 54.075, places=9)
        self.assertAlmostEqual(hs7["expected_rise_K"], 80.4825, places=9)
        self.assertAlmostEqual(hs6["tolerance_K"], 0.270375, places=9)
        manifest = slab049.build_call_list()
        slab = next(a for a in manifest["separate_allocations"] if a["id"] == "known-answer-slab")
        self.assertEqual((slab["calls"], slab["in_this_manifest"], slab["gate_zero_calls"]), (2, False, False))
        self.assertEqual(len(manifest["calls"]), 12)

    def test_the_check_reads_the_die_block(self):
        with tempfile.TemporaryDirectory() as directory:
            steady = Path(directory) / "slab.steady"
            for rise, verdict in ((54.075, "PASS"), (54.30, "PASS"), (80.48, "FAIL")):
                steady.write_text(f"layer_0_die\t{318.15 + rise:.2f}\nlayer_1_TIM\t{318.15 + rise - 1:.2f}\n")
                self.assertEqual(slab049.check_known_answer_slab(Path(directory), "hotspot6")["verdict"], verdict)


if __name__ == "__main__":
    unittest.main()
