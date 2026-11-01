"""SLAB-049's separate, explicitly selected material-only allocation (contract #57399).

Print the tree-generated manifest's SHA-256 with ``python -m sundai_hotspot.coupling_allocation``;
``--write PATH`` also retains its bytes. No command here launches a thermal solve.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from sundai_hotspot import gate0_anchor, gate_zero, slab049

CALL_LIST = slab049.EVIDENCE_DIR / "coupling-call-list.json"
CALL_LIST_SHA256 = "db32a692b749e08324c295e56250f96a9548796aae232ca63f24d2ad4ab3e577"
BINARY_SHA256 = "6ea3b7813412c13d20c92adc6449fbc0bc87c46b521d4d5eaf80b8abc7900609"
KIND = "material_only"
SCHEMA = "sentilab-slab049-coupling-manifest-v1"


def call_list() -> dict:
    data = CALL_LIST.read_bytes()
    if hashlib.sha256(data).hexdigest() != CALL_LIST_SHA256:
        raise slab049.ManifestMismatch("the frozen coupling call list changed")
    return json.loads(data)


def build_manifest() -> dict:
    """Reuse the gate's row format and enforcement policy, with a distinct allocation identity."""
    frozen, gate = call_list(), slab049.build_call_list()
    binary = gate_zero.EVALUATOR_KINDS[KIND]["binary"]
    calls = []
    for listed in frozen["calls"]:
        reference = gate_zero.reference(listed["reference"])
        if (listed["raw_layout_sha256"] != reference.raw_layout_sha256
                or listed["layout_identity"] != reference.layout_identity
                or listed["inputs_sha256"] != gate_zero.frozen_inputs(reference)
                or listed["argv_after_binary"] != slab049.tap_argv(binary, listed["grid"])[1:]):
            raise slab049.ManifestMismatch("coupling inputs differ from the frozen gate reference")
        row = slab049._manifest_call(listed["role"], "hs7", "hotspot7_default", "coupling diagnostic",
                                    reference, listed["grid"], listed["replay_of"])
        if (row["cpu_limit_s"] != listed["cpu_limit_s"]
                or row["accounting"]["reserved_cpu_s"] != listed["envelope_cpu_s"]):
            raise slab049.ManifestMismatch("coupling limits differ from the frozen call list")
        row["command"] = row["command"].replace(row["id"], listed["call"]) + " --manifest coupling"
        row.update(id=listed["call"], engine="hs7material", kind=KIND, binary=binary,
                   binary_sha256=BINARY_SHA256, gating=False,
                   purpose="bounded material-only coupling diagnostic under contract #57399",
                   argv=slab049.tap_argv(f"<private content-addressed copy of {binary}>", listed["grid"]))
        calls.append(row)
    worst = sum(row["accounting"]["reserved_cpu_s"] for row in calls)
    if worst != frozen["total_envelope_cpu_s"]:
        raise slab049.ManifestMismatch("coupling envelope differs from the frozen call list")
    manifest = {key: copy.deepcopy(gate[key]) for key in
                ("operator", "ledger", "anchor", "grant_window", "references", "source")}
    manifest["source"]["allocation_sha256"] = {
        path: slab049._file_sha256(path) for path in (
            "sundai_hotspot/coupling_allocation.py", "sundai_hotspot/reference_validation.py",
            "sundai_hotspot/gate0_operator.py", "sundai_hotspot/gate_zero.py", "sundai_hotspot/provenance.py")}
    manifest.update(
        schema=SCHEMA, ticket="01ac77ac", generated_by="python -m sundai_hotspot.coupling_allocation",
        call_list_sha256=CALL_LIST_SHA256,
        allocation="four calls: two material-only primaries and two fresh-process replays; no gate-zero grant",
        calls=calls,
        evaluation={key: frozen[key] for key in ("statistic", "fraction", "predicate", "references")},
        accounting={"calls": len(calls), "max_runs": len(calls), "retries": 0, "concurrency": 1, "gpu": False,
                    "host_architecture": gate["accounting"]["host_architecture"],
                    "manifest_cpu_cap_s": worst, "worst_case_cpu_s": worst,
                    "limits": slab049.per_call_limits(), "per_call_reserve_cpu_s": slab049.per_call_reserve_s()},
        builds={KIND: {"binary": binary, "binary_sha256": BINARY_SHA256,
                       "provenance": binary + ".provenance.json",
                       "command": gate_zero.EVALUATOR_KINDS[KIND]["build"],
                       "identity_tag": gate_zero.VARIANT_TAG.decode("ascii")}})
    return manifest


def load_manifest(path: Path | None = None) -> tuple[dict, str]:
    generated = slab049._dump(build_manifest())
    if path is not None and Path(path).read_bytes() != generated:
        raise slab049.ManifestMismatch("the coupling manifest is not what this tree generates")
    return json.loads(generated), hashlib.sha256(generated).hexdigest()


def require_binary(call: dict, binary: Path) -> dict:
    """Check the material-only identity tag and the exact operator-image bytes before any launch."""
    identity = gate_zero.evaluator_identity(KIND, binary)
    if identity["binary_sha256"] != call["binary_sha256"]:
        raise gate_zero.GateZeroRefusal("material-only binary SHA-256 differs from the coupling manifest pin")
    return identity


def require_receipt_identity(call: dict, identity: dict) -> None:
    if identity.get("kind") != KIND or identity.get("binary_sha256") != call["binary_sha256"]:
        raise gate_zero.GateZeroRefusal("receipt does not bind the pinned material-only binary")


def evaluate_call(call: dict, directory: Path, record: dict, identity: dict,
                  primary: Path | None = None) -> dict:
    """The gate's native block maximum, with exact decimal input and rational threshold comparison.

    The displayed fraction is decimal; fraction_exact retains the whole rational value, including when
    its decimal expansion repeats. Neither temperature nor fraction is rounded before the predicate.
    Chiplet and active-layer values remain diagnostics, never substitute selectors.
    """
    require_receipt_identity(call, identity)
    if record["effective_package"]["grid_map_mode"] != "center":
        raise gate_zero.GateZeroRefusal("coupling evaluation requires the frozen centre mapping")
    steady = directory / "sample.steady"
    gate_zero.read_steady_values(steady)  # retain the gate's shape, uniqueness and plausibility checks
    values = [(parts[0], Decimal(parts[1])) for line in steady.read_text().splitlines()
              if len(parts := line.split()) == 2 and parts[0] != "Unit"]
    node, kelvin = max(values, key=lambda item: item[1])
    with localcontext() as context:
        context.prec = max(28, len(kelvin.as_tuple().digits) + abs(kelvin.as_tuple().exponent) + 10)
        temperature = kelvin - Decimal("273.15")
    reference = next(row for row in call_list()["references"] if row["reference"] + "-raw" == call["reference"])
    hs7, hs6 = (Decimal(str(reference[key])) for key in ("T_hs7_C", "T_hs6_C"))
    fraction = (Fraction(hs7) - Fraction(temperature)) / (Fraction(hs7) - Fraction(hs6))
    threshold = hs7 - Decimal("0.85") * (hs7 - hs6)
    if threshold != Decimal(str(reference["T_variant_max_for_threshold_C"])):
        raise slab049.ManifestMismatch("the frozen coupling threshold disagrees with its baselines")
    return {
        "statistic": call_list()["statistic"], "T_variant_C": str(temperature),
        "T_hs7_C": str(hs7), "T_hs6_C": str(hs6), "threshold_C": str(threshold),
        "fraction": str(Decimal(fraction.numerator) / Decimal(fraction.denominator)),
        "fraction_exact": str(fraction), "threshold_met": fraction >= Fraction(17, 20),
        "maximizing_node": node,
        "replay_byte_identical": (all((directory / name).read_bytes() == (primary / name).read_bytes()
                                      for name in gate_zero.REPLAY_OUTPUTS) if primary is not None else None),
        "diagnostics": {key: record[key] for key in (
            "chiplet_block_values_C", "chiplet_centre_mapping", "active_layer_grid_peak",
            "spreader_sink_drop_diagnostic", "same_index_stack_at_active_argmax")},
    }


def primary_directory(call: dict, ledger: dict, tags, manifest: dict, digest: str) -> Path | None:
    if call["replay_of"] is None:
        return None
    primary = next(row for row in manifest["calls"] if row["id"] == call["replay_of"])
    try:
        evidence = gate_zero.verify_call(primary, ledger, tags, manifest, digest)["evidence"]
        require_receipt_identity(primary, evidence["receipt"]["evaluator"])
        return evidence["directory"]
    except (gate_zero.GateZeroRefusal, gate0_anchor.AuthenticationError, gate0_anchor.AnchorUnavailable,
            KeyError, TypeError, ValueError):
        return None  # the replay may complete, but no missing/unusable primary can satisfy the predicate


def report(manifest: dict, digest: str, ledger: dict, tags) -> dict:
    """Read the same signed ledger/tag/receipt evidence as gate zero, under this allocation alone."""
    entries, missing = {}, []
    for call in manifest["calls"]:
        entry = {"call": call["id"], "kind": call["kind"], "reference": call["reference"], "grid": call["grid"],
                 "role": call["role"], "replay_of": call["replay_of"], "gating": False, "usable": False}
        try:
            verified = gate_zero.verify_call(call, ledger, tags, manifest, digest)
            evidence = verified["evidence"]
            evaluation = evaluate_call(call, evidence["directory"], evidence["record"],
                                       evidence["receipt"]["evaluator"],
                                       primary_directory(call, ledger, tags, manifest, digest))
            entry.update(usable=True, coupling=evaluation, outputs=evidence["output_sha256"],
                         charged_cpu_s=verified["settlement"].get("charged_cpu_s"),
                         solver_cpu_s=verified["settlement"].get("solver_cpu_s"))
        except (gate_zero.GateZeroRefusal, gate0_anchor.AuthenticationError, gate0_anchor.AnchorUnavailable,
                KeyError, TypeError, ValueError) as exc:
            entry["reason"] = f"{type(exc).__name__}: {exc}"
            missing.append({"call": call["id"], "reason": entry["reason"]})
        entries[call["id"]] = entry
    rows = []
    for call in manifest["calls"]:
        if call["role"] != "primary":
            continue
        primary = entries[call["id"]]
        replay = next(entry for entry in entries.values() if entry["replay_of"] == call["id"])
        pair = (primary.get("coupling", {}), replay.get("coupling", {}))
        identical = pair[1].get("replay_byte_identical")
        failed = any(item.get("threshold_met") is False for item in pair) or identical is False
        complete = primary["usable"] and replay["usable"] and identical is not None
        rows.append({"reference": call["reference"], "temperature_label": gate_zero.TEMPERATURE_LABELS[KIND],
                     "primary": pair[0], "replay": pair[1], "replay_byte_identical": identical,
                     "predicate": False if failed else True if complete else None})
    predicate = (False if any(row["predicate"] is False for row in rows)
                 else True if all(row["predicate"] is True for row in rows) else None)
    return {"schema": "sentilab-slab049-coupling-report-v1", "manifest_sha256": digest,
            "grant_id": ledger["grant"]["grant_id"], "calls": list(entries.values()), "rows": rows,
            "not_completed": missing, "coupling": {"predicate": predicate,
                "verdict": "PASS" if predicate is True else "FAIL" if predicate is False else "INCOMPLETE"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--check-binary", type=Path)
    args = parser.parse_args(argv)
    manifest, digest = load_manifest(args.check)
    if args.check_binary:
        require_binary(manifest["calls"][0], args.check_binary)
    if args.write:
        args.write.write_bytes(slab049._dump(manifest))
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
