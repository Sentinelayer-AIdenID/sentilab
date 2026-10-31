"""Gate zero (SLAB-049): an evaluator identity may be used only after it reproduces published originals.

An evaluator identity is a binary of a known kind. It may produce a result that is used (search, headroom,
rankings, a MATCH claim) only after a recorded gate-zero PASS for that exact binary:

- **Gate.** The paper's two original layouts, as raw reconstructions, must reproduce within the prospective
  computational reference-reproduction tolerance of 1.0 K: Ascend 910 at 75.48 C (Fig. 6(a)) and CPU-DRAM at
  115.94 C (Fig. 5(a)).
- **Out-of-sample validation.** TAP-2.5D's own solutions, Ascend 910 at 75.47 C and CPU-DRAM at 94.89 C, must
  reproduce within the same tolerance whenever their layouts are frozen. A frozen point that fails, fails the gate.
- **Snapped variants.** The legal 1 mm snapped variants are recorded but do not gate.

Source: Ma et al., "TAP-2.5D", DATE 2021. Conditions: 45 mm interposer, 64x64 grid, 45 C ambient and TAP's
package. The metric is TAP-2.5D's own selector (passive_interposer.py run_hotspot): the maximum over HotSpot's
centre-mapped block temperatures, which HotSpot 6.0 prints to stdout and every version writes to the steady file.

The pinned digest covers the references, their roles, the frozen inputs, the tolerance and the metric. Changing
any of them invalidates every existing record.

Nothing here runs a solver.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from sundai_hotspot.tap_oracle import REPO_ROOT

KELVIN_OFFSET = 273.15
TOLERANCE_K = 1.0
TOLERANCE_LABEL = "prospective computational reference-reproduction tolerance"
GRID = 64
INTERPOSER_MM = 45
METRIC = ("block-centre metric: TAP-2.5D run_hotspot selector, the max over the steady file's block "
          "temperatures with grid_map_mode center from TAP's config, 64x64, minus 273.15")
REFERENCE_ROOT = "docs/sentilab/diagnostics/SLAB-049/references"
RECORD_SCHEMA = "sentilab-gate-zero-record-v2"
GATE = "gate"
RAW_NEXT = "raw reconstruction: a separate reference identity, next allocation"
VERIFICATION = "verification case, not a statistical holdout: next allocation"


@dataclass(frozen=True)
class Reference:
    id: str
    role: str
    paper_c: float
    source: str
    inputs: str | None  # frozen TAP inputs (SHA256SUMS lists them); None while the layout is pending


REFERENCES = (
    Reference("ascend910-original-snapped", GATE, 75.48,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 6(a) original layout; legal 1 mm snap",
              f"{REFERENCE_ROOT}/ascend910-original-snapped-45mm"),
    Reference("micro150-original-snapped", GATE, 115.94,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 5(a) original placement; legal 1 mm snap",
              f"{REFERENCE_ROOT}/micro150-original-snapped-45mm"),
    Reference("ascend910-original-raw", RAW_NEXT, 75.48, "Fig. 6(a) original layout, decoded reconstruction",
              f"{REFERENCE_ROOT}/ascend910-original-raw-45mm"),
    Reference("micro150-original-raw", RAW_NEXT, 115.94, "Fig. 5(a) original placement, decoded reconstruction",
              f"{REFERENCE_ROOT}/micro150-original-raw-45mm"),
    Reference("ascend910-tap", VERIFICATION, 75.47, "Ma et al., TAP-2.5D, DATE 2021, Fig. 6(c), TAP-2.5D solution",
              f"{REFERENCE_ROOT}/ascend910-tap-raw-45mm"),
    Reference("micro150-tap", VERIFICATION, 94.89, "Ma et al., TAP-2.5D, DATE 2021, Fig. 5, TAP-2.5D solution "
              "(non-pipelined links); layout pending SLAB-048", None),
)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_digest(reference: Reference, root: Path = REPO_ROOT) -> str | None:
    return None if reference.inputs is None else _sha256(root / reference.inputs / "SHA256SUMS")


def references_sha256(root: Path = REPO_ROOT) -> str:
    """Digest of the pinned references, their roles and frozen inputs, the tolerance and the metric."""
    return hashlib.sha256(_canonical({
        "references": [{**asdict(r), "inputs_sha256sums": inputs_digest(r, root)} for r in REFERENCES],
        "tolerance_k": TOLERANCE_K, "tolerance_label": TOLERANCE_LABEL, "grid": GRID,
        "interposer_mm": INTERPOSER_MM, "metric": METRIC,
    })).hexdigest()


PINNED_REFERENCES_SHA256 = "070002fa42aa5825fff6346a1fb18772e7beb9aa26aab63194c972b7477d4fe6"

# Evaluator kinds. Identity is checked on the bytes that are hashed: required and forbidden markers tell the
# binaries apart, so a mislabelled binary is refused. This guards against mix-ups; it does not authenticate.
VARIANT_TAG = b"SENTILAB_SINK_COUPLING=material_only;ticket=SLAB-049"
HOTSPOT6_TAG = b"SENTILAB_EVALUATOR=hotspot6@a7a3286e;grid_dump=all_layers;ticket=SLAB-049"
HOTSPOT6_COMMIT = "a7a3286e368867c26381e0a23e36b3e273bdeda9"
EVALUATOR_KINDS = {
    "hotspot7_default": {
        "binary": "sundai_hotspot/hotspot",
        "build": "make -C sundai_hotspot -j4 SUPERLU=1",
        "upstream": "uvahotspot/HotSpot f18831e48cef5d62580585cca0d7fab6c71bc3cc (HotSpot 7.0)",
        "required_markers": (b"microchannel",),
        "forbidden_markers": (VARIANT_TAG, b"Unit\tSteady(Kelvin)"),
    },
    "material_only": {
        "binary": "sundai_hotspot/hotspot-material-only",
        "build": "make -C sundai_hotspot SUPERLU=1 hotspot-material-only",
        "upstream": "HotSpot 7.0 f18831e plus the SLAB-049 material-only spreader<->sink link (diagnostic only)",
        "required_markers": (VARIANT_TAG, b"microchannel"),
        "forbidden_markers": (b"Unit\tSteady(Kelvin)",),
    },
    "hotspot6": {
        "binary": "sundai_hotspot6/hotspot",
        "build": "bash scripts/build_hotspot6.sh",
        "upstream": f"uvahotspot/HotSpot {HOTSPOT6_COMMIT} (HotSpot 6.0, TAP-2.5D's version); SuperLU solver, "
                    "all-layer grid dump",
        "required_markers": (b"Unit\tSteady(Kelvin)", HOTSPOT6_TAG, b"dgssv"),
        "forbidden_markers": (b"microchannel", VARIANT_TAG),
    },
    "hotspot6_tap_faithful": {
        "binary": "sundai_hotspot6/hotspot-tap-faithful",
        "build": "bash scripts/build_hotspot6.sh",
        "upstream": f"uvahotspot/HotSpot {HOTSPOT6_COMMIT} unmodified, SUPERLU=0 as TAP-2.5D's util/hotspot was built",
        "required_markers": (b"Unit\tSteady(Kelvin)",),
        "forbidden_markers": (b"microchannel", VARIANT_TAG, b"SENTILAB_EVALUATOR", b"dgssv"),
    },
}


class GateZeroRefusal(RuntimeError):
    """The evaluator has not passed gate zero, or its record does not bind it."""


def evaluator_identity(kind: str, binary: Path) -> dict:
    if kind not in EVALUATOR_KINDS:
        raise GateZeroRefusal(f"unknown evaluator kind {kind!r}")
    path = Path(binary)
    if not path.is_file():
        raise GateZeroRefusal(f"{kind} binary is not built: {path} ({EVALUATOR_KINDS[kind]['build']})")
    data = path.read_bytes()
    spec = EVALUATOR_KINDS[kind]
    missing = [m.decode("ascii", "replace") for m in spec["required_markers"] if m not in data]
    present = [m.decode("ascii", "replace") for m in spec["forbidden_markers"] if m in data]
    if missing or present:
        raise GateZeroRefusal(f"binary does not identify as {kind}: missing {missing}, unexpected {present}")
    return {"kind": kind, "binary_sha256": hashlib.sha256(data).hexdigest(), "upstream": spec["upstream"]}


MAX_PLAUSIBLE_K = 2273.15  # anything hotter is garbage, not a temperature


def read_steady_values(path: Path) -> list[tuple[str, float]]:
    """Block temperatures from a steady file (or HotSpot 6.0 stdout): unique names, finite, plausible Kelvin."""
    values, seen = [], set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] == "Unit":
            continue
        name, value = fields[0], float(fields[1])
        if name in seen:
            raise ValueError(f"duplicate block {name} in {path}")
        if not 0.0 < value <= MAX_PLAUSIBLE_K:  # also rejects nan and inf
            raise ValueError(f"implausible temperature {value} for {name} in {path}")
        seen.add(name)
        values.append((name, value))
    if not values:
        raise ValueError(f"no temperatures in {path}")
    return values


def tap_selector_c(steady: Path) -> tuple[float, str]:
    """TAP's selector on the steady file: (max - 273.15, the block that holds it)."""
    name, kelvin = max(read_steady_values(steady), key=lambda item: item[1])
    return kelvin - KELVIN_OFFSET, name


def tap_stdout_selector_c(stdout: Path) -> float:
    """TAP's literal selector: max(float(stdout.split()[3::2])) - 273.15. Only HotSpot 6.0 prints temperatures."""
    tokens = Path(stdout).read_text(encoding="utf-8", errors="replace").split()
    return max(map(float, tokens[3::2])) - KELVIN_OFFSET


def frozen_inputs(reference: Reference, root: Path = REPO_ROOT) -> dict[str, str]:
    if reference.inputs is None:
        raise GateZeroRefusal(f"{reference.id}: the reference layout is pending")
    sums = {}
    for line in (root / reference.inputs / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest
    return sums


def _within(measured_c: float, reference: Reference) -> bool:
    return abs(measured_c - reference.paper_c) <= TOLERANCE_K


RECEIPT_SCHEMA = "sentilab-reference-validation-receipt-v1"


def build_record(kind: str, binary: Path, run_dirs: dict[str, Path], root: Path = REPO_ROOT) -> dict:
    """Gate-zero record from validate-reference run directories (reads files only).

    Each directory holds the receipt written by `reference_validation validate-reference` and the solver outputs.
    The receipt must name this binary, the frozen inputs must be byte-identical, the grid must be 64, and the
    metric is recomputed from the steady file (receipt numbers are not trusted).
    """
    identity = evaluator_identity(kind, binary)
    results = []
    for reference in REFERENCES:
        if reference.id not in run_dirs:
            if reference.role == GATE:
                raise GateZeroRefusal(f"no run directory for the gate reference {reference.id}")
            continue
        directory = Path(run_dirs[reference.id])
        receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
        if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("reference") != reference.id:
            raise GateZeroRefusal(f"{reference.id}: not a validate-reference receipt for this reference")
        if receipt.get("evaluator", {}).get("binary_sha256") != identity["binary_sha256"]:
            raise GateZeroRefusal(f"{reference.id}: the receipt was produced by a different binary")
        if receipt.get("grid") != GRID or receipt.get("exit_status") != 0:
            raise GateZeroRefusal(f"{reference.id}: gate zero needs a completed grid-{GRID} solve")
        for name, digest in frozen_inputs(reference, root).items():
            if _sha256(directory / name) != digest:
                raise GateZeroRefusal(f"{reference.id}: {name} is not the frozen reference input")
        measured, block = tap_selector_c(directory / "sample.steady")
        literal = None
        if kind.startswith("hotspot6"):
            literal = tap_stdout_selector_c(directory / "stdout.txt")
            if abs(literal - measured) > 1e-9:
                raise GateZeroRefusal(f"{reference.id}: stdout and steady-file selectors disagree")
        results.append({"id": reference.id, "role": reference.role, "paper_c": reference.paper_c,
                        "measured_c": measured, "selector_block": block, "stdout_selector_c": literal,
                        "delta_k": measured - reference.paper_c, "within_tolerance": _within(measured, reference),
                        "config_sha256": _sha256(directory / "new_hotspot.config"),
                        "steady_sha256": _sha256(directory / "sample.steady"),
                        "receipt_sha256": _sha256(directory / "receipt.json")})
    # Gate references must pass; any other pinned published value that was measured must not be contradicted.
    passed = all(r["within_tolerance"] for r in results)
    return {"schema": RECORD_SCHEMA, "evaluator": identity, "references_sha256": references_sha256(root),
            "tolerance_k": TOLERANCE_K, "tolerance_label": TOLERANCE_LABEL, "metric": METRIC,
            "results": results, "verdict": "PASS" if passed else "FAIL"}


def require_gate_zero(kind: str, binary: Path, record: Path | dict | None, root: Path = REPO_ROOT) -> dict:
    """Refuse unless `record` is a PASS for exactly this evaluator kind and binary against the pinned references.

    The verdict is recomputed from the measured values; a record's own verdict is never trusted. Search and
    headroom call this before any evaluation. Producing the first receipt does not (reference_validation).
    """
    if record is None:
        raise GateZeroRefusal(f"{kind} has no gate-zero PASS receipt; search and headroom may not use it until it "
                              f"reproduces the pinned originals within the {TOLERANCE_LABEL} ({TOLERANCE_K} K)")
    data = json.loads(Path(record).read_text(encoding="utf-8")) if not isinstance(record, dict) else record
    identity = evaluator_identity(kind, binary)
    if data.get("schema") != RECORD_SCHEMA:
        raise GateZeroRefusal("gate-zero record has the wrong schema")
    current = references_sha256(root)
    if current != PINNED_REFERENCES_SHA256 or data.get("references_sha256") != PINNED_REFERENCES_SHA256:
        raise GateZeroRefusal("gate-zero references are not the pinned set")
    if data.get("evaluator", {}).get("kind") != kind or data["evaluator"].get("binary_sha256") != identity["binary_sha256"]:
        raise GateZeroRefusal("gate-zero record belongs to a different evaluator binary")
    pinned = {r.id: r for r in REFERENCES}
    results = data.get("results", [])
    for reference in REFERENCES:
        if reference.role == GATE and not any(r.get("id") == reference.id for r in results):
            raise GateZeroRefusal(f"gate-zero record lacks the gate reference {reference.id}")
    for result in results:
        reference = pinned.get(result.get("id"))
        if reference is None or result.get("paper_c") != reference.paper_c:
            raise GateZeroRefusal(f"gate-zero record has an unpinned result {result.get('id')!r}")
        measured = float(result["measured_c"])
        if not _within(measured, reference):
            raise GateZeroRefusal(f"{kind} misses {reference.id} by {measured - reference.paper_c:+.2f} K "
                                  f"(the {TOLERANCE_LABEL} is {TOLERANCE_K} K)")
    if data.get("verdict") != "PASS":
        raise GateZeroRefusal("gate-zero record is not a PASS")
    return data
