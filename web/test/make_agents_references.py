"""The agent site's copies of the SLAB-048 reference layouts (web/public/agents/references/).

    python web/test/make_agents_references.py --source <dir> --write    (regenerate the copies)
    python web/test/make_agents_references.py --source <dir> --check    (exit 1 if a copy differs)

<dir> holds the four reference files of docs/sentilab/references/ (SLAB-048, PR #57); it defaults to that folder in
this tree. In each raw file the raw section is frozen as reviewed, and its identity, role and continuous-rules result
live beside it in raw_annotations; the copies take each from where it is.
Each copy keeps the layout's geometry, identity, legality, routed and proxy wire and provenance, value for value, under
the agent site's labels. It leaves out every temperature, every paper-reported value, internal notes and the 1 mm
history variant; each file lists what it leaves out and why. Numbers keep their JSON form (45.0 stays a float), so
identity.content_sha256 recomputes from identity.canonical exactly as identity.hashing says. The copies are written the
way the sources are (indent 1, sorted keys, ASCII, LF), and copied_from names each source file with its SHA-256; the
node test (agents-site.test.mjs) checks those hashes whenever the sources are in the tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "agents" / "references"
DEFAULT_SOURCE = ROOT / "docs" / "sentilab" / "references"
SOURCE_PATH = "docs/sentilab/references/"
REFERENCES = ("ascend910-tap25d-fig6a", "micro150-tap25d-fig5a")
NL = chr(10)

RAW_LABEL = "reconstructed from a published figure, continuous, reference-only"
RAW_ROLE = ("The comparator R. It is scored by the same evaluator, router and rules as every proposal. Its centres are "
            "continuous and sit off the 500 um lattice, so it is reference-only and never an admissible entry.")
VARIANT_LABEL = "engineering variant"
VARIANT_ROLE = ("Engineering comparison and sensitivity baseline, legal on the fixture as rounded: the raw centres rounded "
                "to the nearest 0.5 mm, rotations kept, no repair moves. It is not the paper's layout, never a paper "
                "match, and not part of gate zero.")
UNCERTAINTY_NOTE = ("Per coordinate (L-infinity), an empirical estimate under stated assumptions of the error in reading "
                    "the figure: the largest offset found on TAP-2.5D's own placer panels from their 1 mm grid, plus the "
                    "coordinate times the relative spread of the panel's three scale estimates, plus the 5e-5 mm storage "
                    "step, rounded up to 1e-4 mm. It covers reading the figure only. It is not a figure-to-silicon error "
                    "bound, and how faithfully the figure shows the authors' simulated layout cannot be read from it.")
WIRE_NOTE = ("routed_wirelength is this layout's routed wire W, from the open router (TAP-2.5D's MILP router ported from "
             "CPLEX to HiGHS), the wire figure the challenge judges. It depends only on the dies' relative positions: "
             "moving the whole layout leaves it unchanged. wire_proxy_mm is the proxy W_proxy, the connectivity-weighted "
             "mean Manhattan distance between die centres, a diagnostic that is never used to judge. Neither runs a "
             "thermal solve.")
OMITTED_RAW = [
    {"fields": ["paper_reported", "paper_settings", "round_trip", "validation_points"],
     "why": "temperatures and paper-reported values: these pages show no temperatures, and published targets are kept "
            "in separate fields of the signed manifest (the router identity is kept in routed_wirelength)"},
    {"fields": ["snapped", "raw_to_snapped_mm", "raw_to_snapped_norms", "max_abs_raw_to_snapped_mm"],
     "why": "the 1 mm snapped variant: kept as history in the source record, superseded as the baseline, not part of "
            "this site"},
    {"fields": ["raw.label", "raw.role", "track", "wire_metric"],
     "why": "superseded wording, replaced by this file's label, role and wire_note"},
    {"fields": ["decoding", "raw.how_obtained", "raw.decoded_size_mm", "raw.uncertainty_rule",
                "raw.fixture_gate_message", "raw_annotations.uncertainty_statement",
                "raw_annotations.continuous_rules_check", "raw_annotations.role", "raw_annotations.frozen",
                "raw_annotations.reviewed_at", "raw_annotations.section_sha256", "snapped_annotations",
                "interposer_mm", "schema", "ticket.uuid"],
     "why": "figure-extraction and record internals; the uncertainty rule is restated in center_uncertainty_note"},
]
OMITTED_VARIANT = [
    {"fields": ["routed_wirelength.vs_paper_pct"],
     "why": "a paper-reported comparison: published targets are kept in separate fields of the signed manifest"},
    {"fields": ["one_mm_snapped_for_comparison"],
     "why": "the 1 mm snapped variant: kept as history in the source record, not part of this site"},
    {"fields": ["decision", "role", "label"],
     "why": "internal attribution and superseded wording, replaced by this file's label and role"},
    {"fields": ["sources", "schema", "variant_id", "ticket.uuid"],
     "why": "record internals; layout_id is the variant_id, and source names the published figure"},
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def provenance(name: str, data: bytes) -> dict:
    return {"record": "SLAB-048 reference layouts", "path": SOURCE_PATH + name, "file_sha256": sha256(data)}


def routed(value: float, router: dict) -> dict:
    return {"value_mm": value, "label": router["label"], "router": router["router"],
            "router_sha256": router["router_sha256"], "solver": router["solver"], "status": "provisional",
            "frozen": False, "router_acceptance": "UNKNOWN: router acceptance is pending"}


def raw_copy(src: dict, name: str, data: bytes) -> dict:
    raw, notes, wire = src["raw"], src["raw_annotations"], src["round_trip"]["wire"]
    if wire["routed_wirelength_mm"] != raw["routed_wirelength_mm"] or wire["layout"] != "raw":
        raise ValueError(f"{name}: the router record does not describe the raw layout")
    canonical = notes["identity"]["canonical"]
    if (canonical["centers_mm"], canonical["rotated"], canonical["footprints_mm"]) != (
            raw["centers_mm"], raw["rotated"], raw["footprints_mm"]):
        raise ValueError(f"{name}: raw_annotations.identity does not describe the raw section")
    return {
        "schema": "sentilab-agents-reference/1", "layout_id": src["reference_id"] + "/raw",
        "reference_id": src["reference_id"], "kind": "raw", "label": RAW_LABEL, "role": RAW_ROLE,
        "title": src["title"], "labels": src["labels"], "claim_label": src["claim_label"], "source": src["source"],
        "fixture": src["fixture"], "units": canonical["units"], "dies": src["dies"],
        "centers_mm": raw["centers_mm"], "rotated": raw["rotated"], "footprints_mm": raw["footprints_mm"],
        "lower_left_mm": raw["lower_left_mm"], "center_uncertainty_mm": raw["center_uncertainty_mm"],
        "center_uncertainty_note": UNCERTAINTY_NOTE, "legal_on_fixture": raw["legal_on_fixture"],
        "violations_on_fixture": raw["violations_on_fixture"], "continuous_rules_legal": notes["continuous_rules_legal"],
        "violations_without_center_lattice": raw["violations_without_center_lattice"],
        "identity": notes["identity"], "design_hash": raw["design_hash"],
        "routed_wirelength": routed(raw["routed_wirelength_mm"], {
            "label": wire["routed_label"], "router": wire["router"], "router_sha256": wire["router_sha256"],
            "solver": wire["solver"]}),
        "wire_proxy_mm": raw["wire_proxy_mm"], "wire_note": WIRE_NOTE, "model_omissions": src["model_omissions"],
        "ticket": {"id": src["ticket"]["id"], "name": src["ticket"]["name"]},
        "copied_from": [provenance(name, data)], "omitted": OMITTED_RAW,
    }


def variant_copy(var: dict, src: dict, name: str, data: bytes, raw_name: str, raw_data: bytes) -> dict:
    if var["derived_from"]["reference_id"] != src["reference_id"] or var["fixture"] != src["fixture"]:
        raise ValueError(f"{name}: not derived from {raw_name}")
    wire = var["routed_wirelength"]
    return {
        "schema": "sentilab-agents-reference/1", "layout_id": var["variant_id"],
        "reference_id": var["derived_from"]["reference_id"], "kind": "engineering-variant", "label": VARIANT_LABEL,
        "role": VARIANT_ROLE, "labels": var["labels"], "derived_from": var["derived_from"],
        "rounding_rule": var["rounding_rule"], "repair_moves": var["repair_moves"],
        "is_the_paper_layout": var["is_the_paper_layout"], "source": src["source"], "fixture": var["fixture"],
        "units": var["units"], "dies": src["dies"], "centers_mm": var["centers_mm"], "rotated": var["rotated"],
        "footprints_mm": var["footprints_mm"], "legal_on_fixture": var["legal_on_fixture"],
        "raw_inside_pm0p5_mm_per_coordinate_box": var["raw_inside_pm0p5_mm_per_coordinate_box"],
        "displacement_from_raw": var["displacement_from_raw"], "identity": var["identity"],
        "design_hash": var["design_hash"],
        "routed_wirelength": routed(wire["value_mm"], {
            "label": wire["label"], "router": wire["router"], "router_sha256": wire["router_sha256"],
            "solver": wire["solver"]}),
        "wire_proxy_mm": var["wire_proxy_mm"], "wire_note": WIRE_NOTE, "limits": var["limits"],
        "ticket": {"id": var["ticket"]["id"], "name": var["ticket"]["name"]},
        "copied_from": [provenance(name, data), provenance(raw_name, raw_data)], "omitted": OMITTED_VARIANT,
    }


def serialize(value: dict) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + NL).encode("ascii")


def build(source: Path) -> dict[str, bytes]:
    out = {}
    for ref in REFERENCES:
        raw_name, var_name = ref + ".json", ref + "-snap0p5.json"
        raw_data, var_data = (source / raw_name).read_bytes(), (source / var_name).read_bytes()
        raw_src, var_src = json.loads(raw_data), json.loads(var_data)
        out[raw_name] = serialize(raw_copy(raw_src, raw_name, raw_data))
        out[var_name] = serialize(variant_copy(var_src, raw_src, var_name, var_data, raw_name, raw_data))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    copies = build(args.source)
    stale = [name for name, data in copies.items()
             if not (OUT / name).is_file() or (OUT / name).read_bytes() != data]
    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, data in copies.items():
            (OUT / name).write_bytes(data)
        print(f"wrote {len(copies)} copies ({len(stale)} changed)")
        return 0
    for name in stale:
        print(f"stale: {name}", file=sys.stderr)
    print("copies match their sources" if not stale else f"{len(stale)} stale")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
