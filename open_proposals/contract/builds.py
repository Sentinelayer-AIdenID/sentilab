"""Evaluator builds a temperature label names exactly (contracts/open-proposal-v1/builds.json). The scoped
"reproduction_tested" state belongs to one complete build identity, and to nothing else.

A build's identity is {schema, engine, engine_commit, binary_sha256, image, config_sha256, grid, centre_mapping}. Its
identity string (build_id) names it in the evaluator-identity form the pages already use, then seals it:

  <engine>:<engine_commit>:binary_sha256:<binary>:config_sha256:<sha256 of the config file map>:grid:<n>x<n>
  :build_sha256:<sha256 of the whole identity's canonical JSON>

The readable fields say which build it is; build_sha256 covers every field, the image and the centre mapping
included, so a change to any one field is another string. The broad alias "hotspot6:<binary>:grid:64x64", a
single-field variant and every other string are other evaluators and read unvalidated. The string keeps the label
rule's "engine:commit" key first, so a withdrawn engine stays withdrawn whatever follows it.

The gate-zero build is derived from the repository, not typed (derive_gate0_identity):
  engine_commit   sundai_hotspot6/UPSTREAM_COMMIT, which the golden manifest's statistic.evaluator.upstream repeats
  binary_sha256   the door scorer's pin (app/door/scorer.py EVALUATOR_BINARY_SHA256); door-scorer pins the same binary
  config_sha256   every input file both gate-zero raw references share, by their pinned SHA256SUMS: the HotSpot config
                  (grid size and centre map mode included), the layer stack and the package layers' floorplans; not
                  the per-layout power trace and die floorplans
  grid            sundai_hotspot/gate_zero.py GRID, which the manifest's statistic.grid repeats
  centre_mapping  the golden manifest's statistic.centre_mapping
  image           the one value from outside the repository: the operator-reported image tag in the evaluator binding
                  packet, recorded with that packet's sha256. A tag is mutable: it names the build and proves nothing

Beside the identity, outside the string, each build records image_digest: its image's sha256 digest, from the same
packet (evaluator.image_id_or_digest), or null when none is recorded. It is the only proof of a run's image: the door
names a build only when the run's evaluation receipt and its signed grant both carry exactly that digest
(app/door/evaluator.py), and a null digest is never matched. The packet records none for the gate-zero image, so no
door run is that build until a digest is recorded.

  python -m open_proposals.contract.builds --write --receipts GATE0.json REDERIVATION.json --binding PACKET.json
  python -m open_proposals.contract.builds --check     # exit 1 unless builds.json matches its sources

--write reads the gate-zero receipt and its independent re-derivation (Senti room messages 57377 and 57394, saved as
`sl session read --json` writes them) and records their values with each message's sha256, keeping the native
all-block maximum, the chiplet-centre mean and the active-layer peak apart; --out writes elsewhere (to compare). --check
re-derives every repository field and, where web/public/agents/evidence.json is present (not in the API image),
cross-checks the recorded receipts and reference values against it.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import sys
from pathlib import Path

from .canonical import digest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "contracts" / "open-proposal-v1"
BUILDS_PATH = CONTRACT_DIR / "builds.json"
EVIDENCE = Path("web") / "public" / "agents" / "evidence.json"
BUILDS_SCHEMA = "sentilab-evaluator-builds/1"
BUILD_SCHEMA = "sentilab-evaluator-build/1"
IDENTITY_FIELDS = ("schema", "engine", "engine_commit", "binary_sha256", "image", "config_sha256", "grid",
                   "centre_mapping")
ENGINE = "HotSpot-6.0"                      # the engine name HotSpot 6.0 identities use (sundai_hotspot/evaluators.py)
LABEL = "reproduction_tested"
REFERENCES_DIR = Path("docs") / "sentilab" / "diagnostics" / "SLAB-049" / "references"
GATE0_CASES = {"ascend910-tap25d-fig6a/raw": "ascend910-tap25d-fig6a-raw-45mm",
               "micro150-tap25d-fig5a/raw": "micro150-tap25d-fig5a-raw-45mm"}
RECEIPT_NAMES = {"Ascend 910": "ascend910-tap25d-fig6a/raw", "CPU-DRAM": "micro150-tap25d-fig5a/raw"}
GATE0_SEQ, REDERIVATION_SEQ = 57377, 57394
RULE = ("Exact match only. A build's identity string is <engine>:<engine_commit>:binary_sha256:<binary>"
        ":config_sha256:<sha256 of the config file map>:grid:<n>x<n>:build_sha256:<sha256 of the canonical identity>, "
        "the identity being schema, engine, engine_commit, binary_sha256, image, config_sha256, grid and "
        "centre_mapping. Any other string, the broad alias hotspot6:<binary>:grid:64x64 included, is another "
        "evaluator. A run is a build only when its image is proved by digest: its evaluation receipt's image_digest "
        "and its signed grant's scorer_image_digest are both the build's recorded image_digest. A tag never counts, "
        "and a build whose image_digest is null is never matched. The label is the build's: it never clears a "
        "result's own qualifiers (diagnostic, unassociated, replay status).")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=-]{0,63}")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
NO_DIGEST = ("the packet records no digest for this image (null), so no run is matched to this build until one is "
             "recorded")
STATISTICS = {
    "native_all_block_max_C": "gate zero's statistic: the maximum native block output under centre mapping, compared "
                              "with the paper's value within tolerance_K",
    "max_chiplet_centre_cell_mean_C": "the door board's statistic: the maximum over the real chiplets of the mean of "
                                      "each one's central grid cells; another statistic, recorded beside the first",
    "active_layer_peak_C": "the active layer's grid maximum; a third statistic",
}


def _token(value) -> str:
    """A readable field as written (a string token or an integer), else "unknown"; build_sha256 keeps it exact."""
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    return text if isinstance(text, str) and TOKEN.fullmatch(text) else "unknown"


def build_id(identity: dict) -> str:
    """The identity string of a build identity (module docstring). It always matches the contract's evaluator
    pattern; a field that is missing or not a plain token reads "unknown" in the readable part."""
    if not isinstance(identity, dict) or sorted(identity) != sorted(IDENTITY_FIELDS) or \
            identity["schema"] != BUILD_SCHEMA:
        raise ValueError("a build identity has exactly its fields")
    grid = _token(identity["grid"])
    return (f"{_token(identity['engine'])}:{_token(identity['engine_commit'])}"
            f":binary_sha256:{_token(identity['binary_sha256'])}:config_sha256:{digest(identity['config_sha256'])}"
            f":grid:{grid}x{grid}:build_sha256:{digest(identity)}")


def _digest_recorded(build: dict) -> bool:
    """The build records image_digest: sha256: and 64 lower-case hex, or null when none is recorded."""
    if "image_digest" not in build:
        return False
    value = build["image_digest"]
    return value is None or (isinstance(value, str) and IMAGE_DIGEST.fullmatch(value) is not None)


def load(path: Path = BUILDS_PATH) -> tuple:
    """The registered builds: each id checked against its identity, each image digest well-formed or null, and each
    id registered once, so an id stands for exactly one recorded digest."""
    record = json.loads(path.read_bytes())
    if record.get("schema") != BUILDS_SCHEMA:
        raise ValueError("not a builds registry")
    for build in record["builds"]:
        if build["id"] != build_id(build["identity"]) or build["label"] != LABEL:
            raise ValueError("a registered build's id does not match its identity")
        if not _digest_recorded(build):
            raise ValueError("a registered build records its image digest (sha256:<64 hex>) or null")
    ids = [build["id"] for build in record["builds"]]
    if len(set(ids)) != len(ids):
        raise ValueError("a build is registered once")
    return tuple(record["builds"])


@functools.lru_cache(maxsize=1)
def registered() -> tuple:
    return load()


def _sums(case_dir: str, root: Path) -> dict:
    text = (root / REFERENCES_DIR / case_dir / "SHA256SUMS").read_text(encoding="ascii")
    return {name: value for value, name in (line.split("  ", 1) for line in text.splitlines() if line.strip())}


def shared_config(root: Path = ROOT) -> dict:
    """Every input file both gate-zero raw references share, by hash: the configuration their build ran with."""
    first, second = (_sums(case_dir, root) for case_dir in GATE0_CASES.values())
    shared = {name: value for name, value in sorted(first.items()) if second.get(name) == value}
    if "new_hotspot.config" not in shared:
        raise ValueError("the gate-zero references do not share their HotSpot config")
    return shared


def _constant(path: Path, name: str, pattern: str) -> str:
    match = re.search(rf"^{name} = {pattern}$", path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError(f"{name} not found in {path.name}")
    return match.group(1)


def derive_gate0_identity(image: str, root: Path = ROOT) -> dict:
    """The gate-zero build's identity from its sources, given its image tag; ValueError if two sources disagree."""
    golden = json.loads((root / "contracts/open-proposal-v1/golden/manifests.json").read_bytes())
    statistic = golden["manifests"]["M"]["statistic"]
    commit = (root / "sundai_hotspot6" / "UPSTREAM_COMMIT").read_text(encoding="ascii").strip()
    grid = int(_constant(root / "sundai_hotspot/gate_zero.py", "GRID", r"(\d+)"))
    if statistic["evaluator"]["upstream"] != commit or statistic["grid"] != grid:
        raise ValueError("the manifest and the repository name different engine commits or grids")
    return {"schema": BUILD_SCHEMA, "engine": ENGINE, "engine_commit": commit,
            "binary_sha256": _constant(root / "app/door/scorer.py", "EVALUATOR_BINARY_SHA256", r'"([0-9a-f]{64})"'),
            "image": image, "config_sha256": shared_config(root), "grid": grid,
            "centre_mapping": statistic["centre_mapping"]}


def _message(path: Path, seq: int) -> dict:
    events = json.loads(Path(path).read_bytes())["events"]
    event = next(item for item in events if item.get("sequenceId") == seq)
    text = event["payload"]["message"]
    return {"room": event["sessionId"][:8], "seq": seq, "author": event["agent"]["id"],
            "at": event["ts"][:23] + "Z", "message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text}


def _number(text: str) -> float:
    return float(text.replace("−", "-"))


def _find(pattern: str, text: str):
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"the receipt does not read as expected: {pattern}")
    return match


def parse_receipts(gate0: Path, rederivation: Path) -> dict:
    """The two receipts' values, read from their own text: receipts, references, tolerance and precision."""
    first, second = _message(gate0, GATE0_SEQ), _message(rederivation, REDERIVATION_SEQ)
    rows = re.findall(r"\| (Ascend 910|CPU-DRAM) \(TAP-2\.5D Fig\. \w+\) \| ([\d.]+) °C \| \*\*([\d.]+) °C\*\* "
                      r"\| ([−-]?[\d.]+) K \| ([a-z-]+) \| ([\d.]+) \|", first["text"])
    if [row[0] for row in rows] != list(RECEIPT_NAMES):
        raise ValueError("the gate-zero receipt's table does not read as expected")
    centre = _find(r"chiplet-centre averages are ([\d.]+)/([\d.]+) C", second["text"])
    active = _find(r"active-layer peaks are ([\d.]+)/([\d.]+) C", second["text"])
    references = []
    for index, (name, paper, native, delta, replay, grid32) in enumerate(rows):
        references.append({"case": RECEIPT_NAMES[name], "paper_C": _number(paper),
                           "native_all_block_max_C": _number(native), "delta_K": _number(delta), "replay": replay,
                           "grid32_native_all_block_max_C": _number(grid32),
                           "max_chiplet_centre_cell_mean_C": _number(centre.group(index + 1)),
                           "active_layer_peak_C": _number(active.group(index + 1))})
    run = _find(r"merged build (\w+) \(tree (\w+)\), manifest (\w+), grant `([^`]+)`", first["text"])
    keep = ("room", "seq", "author", "at", "message_sha256")
    receipts = [
        {key: first[key] for key in keep} | {
            "verdict": _find(r"\*\*Gate zero: (PASS)\.\*\*", first["text"]).group(1),
            "scope": _find(r"\*\*Scope of the PASS:\*\* ([^\n]+)", first["text"]).group(1),
            "build": run.group(1), "tree": run.group(2), "manifest": run.group(3), "grant": run.group(4)},
        {key: second[key] for key in keep} | {
            "verdict": _find(r"Gate zero: (independent saved-artifact re-derivation confirms the numerical PASS)",
                             second["text"]).group(1),
            "metric": _find(r"Keep the metric exact: ([^.]+)\.", second["text"]).group(1),
            "report_sha256": _find(r"Root report ([0-9a-f]{64})", second["text"]).group(1),
            "packet_seal_sha256": _find(r"packet seal ([0-9a-f]{64})", second["text"]).group(1)}]
    return {"receipts": receipts, "references": references,
            "tolerance_K": _number(_find(r"prospective (\d+) K bar", second["text"]).group(1)),
            "raw_precision_K": _number(_find(r"Raw precision is ([\d.]+) K", second["text"]).group(1))}


def write(gate0: Path, rederivation: Path, binding: Path, path: Path = BUILDS_PATH) -> dict:
    raw = Path(binding).read_bytes()
    evaluator = json.loads(raw)["evaluator"]
    identity = derive_gate0_identity(evaluator["image_tag_operator_reported"])
    if (evaluator["binary_sha256"] != identity["binary_sha256"] or evaluator["grid"] != identity["grid"]
            or evaluator["base_reference_config_sha256"] != identity["config_sha256"]["new_hotspot.config"]
            or identity["engine_commit"] not in evaluator["upstream"]):
        raise ValueError("the binding packet and the repository describe different builds")
    image_digest = evaluator["image_id_or_digest"]
    if not _digest_recorded({"image_digest": image_digest}):
        raise ValueError("the binding packet's image digest is neither a sha256 image digest nor null")
    packet = hashlib.sha256(raw).hexdigest()
    record = {"schema": BUILDS_SCHEMA, "rule": RULE, "builds": [{
        "id": build_id(identity), "label": LABEL, "identity": identity, "image_digest": image_digest,
        "sources": {
            "engine_commit": "sundai_hotspot6/UPSTREAM_COMMIT (= golden manifest statistic.evaluator.upstream)",
            "binary_sha256": "app/door/scorer.py EVALUATOR_BINARY_SHA256 (door-scorer pins the same binary)",
            "image": {"field": "evaluator.image_tag_operator_reported", "packet_sha256": packet,
                      "note": "operator-reported tag: it names the build and proves no image (image_digest does)"},
            "image_digest": {"field": "evaluator.image_id_or_digest", "packet_sha256": packet,
                             "note": NO_DIGEST if image_digest is None else "the image digest the packet records"},
            "config_sha256": "the input files both gate-zero raw references share: "
                             + ", ".join(f"{REFERENCES_DIR.as_posix()}/{name}/SHA256SUMS"
                                         for name in GATE0_CASES.values()),
            "grid": "sundai_hotspot/gate_zero.py GRID (= golden manifest statistic.grid)",
            "centre_mapping": "golden manifest statistic.centre_mapping"},
        **parse_receipts(gate0, rederivation), "statistics": STATISTICS}]}
    path.write_bytes((json.dumps(record, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    return record


def check(path: Path = BUILDS_PATH, root: Path = ROOT) -> list:
    """Every disagreement between builds.json and its sources; empty when it holds."""
    found = []
    record = json.loads(path.read_bytes())
    if record.get("schema") != BUILDS_SCHEMA or record.get("rule") != RULE:
        found.append("schema or rule")
    tolerance = float(_constant(root / "sundai_hotspot/gate_zero.py", "TOLERANCE_K", r"([\d.]+)"))
    evidence = json.loads((root / EVIDENCE).read_bytes())["gate_zero"] if (root / EVIDENCE).exists() else None
    for build in record["builds"]:
        identity = build["identity"]
        if build["id"] != build_id(identity) or build["label"] != LABEL or build["statistics"] != STATISTICS:
            found.append("id, label or statistics")
        if not _digest_recorded(build):
            found.append("image_digest")
        derived = derive_gate0_identity(identity["image"], root)
        found += [f"identity.{name}" for name in IDENTITY_FIELDS if identity[name] != derived[name]]
        if build["tolerance_K"] != tolerance:
            found.append("tolerance_K")
        for reference in build["references"]:
            delta = reference["native_all_block_max_C"] - reference["paper_C"]
            if abs(delta) > tolerance or round(delta, 2) != reference["delta_K"]:
                found.append(f"references.{reference['case']}.delta_K")
        if evidence is not None:
            found += _against_evidence(build, evidence)
    return found


def _against_evidence(build: dict, evidence: dict) -> list:
    """The committed public evidence record says the same: build, tree, review, and each reference's statistics."""
    found = []
    gate0, rederivation = build["receipts"]
    source = evidence["source"]
    if not (source["merged_commit"].startswith(gate0["build"]) and source["tree"].startswith(gate0["tree"])
            and source["independent_review_sha256"] == rederivation["report_sha256"]):
        found.append("receipts")
    if evidence["engine"] != "HotSpot 6.0" or evidence["grid"] != [build["identity"]["grid"]] * 2:
        found.append("engine or grid")
    rows = {row["layout"]: row for row in evidence["results"]}
    pairs = (("paper_C", "paper_native_target_C"), ("native_all_block_max_C", "native_block_max_C"),
             ("max_chiplet_centre_cell_mean_C", "chiplet_centre_average_max_C"),
             ("active_layer_peak_C", "active_layer_grid_peak_C"))
    if sorted(rows) != sorted(GATE0_CASES) or sorted(item["case"] for item in build["references"]) != sorted(rows):
        found.append("references")
    for reference in build["references"]:
        row = rows.get(reference["case"])
        if row is None or any(reference[ours] != row[theirs] for ours, theirs in pairs):
            found.append(f"references.{reference['case']}")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m open_proposals.contract.builds")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--receipts", nargs=2, type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--out", type=Path, default=BUILDS_PATH)
    args = parser.parse_args(argv)
    if args.write:
        print(write(args.receipts[0], args.receipts[1], args.binding, args.out)["builds"][0]["id"])
        return 0
    found = check()
    print("builds.json matches its sources" if not found else "mismatches: " + ", ".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
