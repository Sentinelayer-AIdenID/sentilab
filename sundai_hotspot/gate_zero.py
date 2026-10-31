"""Gate zero (SLAB-049): an evaluator identity may be used only after it reproduces the paper's published originals.

An evaluator identity is a binary of a known kind. It may produce a result that is used (search, headroom,
rankings, a MATCH claim) only after a recorded gate-zero PASS for that exact binary. Everything below is frozen
before any run (root #56858; astra supplement on PR #56, comment 6545712065):

- **Gate: two raw paper-match references.** TAP-2.5D's two original layouts as SLAB-048 decoded them from the
  paper's vector figures, raw: the continuous centres and the rotations as drawn, never snapped. Ascend 910 at
  75.48 C (Fig. 6(a)) and CPU-DRAM at 115.94 C (Fig. 5(a)). Each is pinned by its raw layout's own content hash.
- **The frozen predicate.** On the native6 target (the HotSpot 6.0 evaluator build) at grid 64, each reference's
  primary call and its fresh-process replay must each reproduce the paper within the prospective computational
  reference-reproduction tolerance of 1.0 K, and each replay's outputs must be byte-identical to its primary's.
  A completed miss gives FAIL. A required outcome that is missing, unsettled or incomplete gives INCOMPLETE: STOP,
  never PASS.
- **Deferred, declared now.** TAP-2.5D's own solutions (Ascend 910 at 75.47 C, Fig. 6(c); CPU-DRAM at 94.89 C,
  Fig. 5(c)) are verification points for a later allocation. They have no calls here, cannot pass or fail this
  gate, and every record lists them as pending verification.
- **Snapped variants are other identities.** A legal snapped variant is an engineering comparison. It never carries
  the raw paper-match claim and cannot enter a gate-zero record.

Source: Ma et al., "TAP-2.5D", DATE 2021. Conditions: 45 mm interposer, 64x64 grid, 45 C ambient and TAP's
package. The metric is TAP-2.5D's own selector (passive_interposer.py run_hotspot): the maximum over HotSpot's
centre-mapped block temperatures, which HotSpot 6.0 prints to stdout and every version writes to the steady file.

A record is assembled from the grant's ledger of admitted calls, by call id, never from directories a caller
chooses, and every result is re-derived from the retained raw evidence. The pinned digest covers the references,
their roles and pins, the frozen inputs, the predicate, the tolerance and the metric; changing any of them
invalidates every record.

Nothing here runs a solver.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
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
RAW_LAYOUT_ROOT = f"{REFERENCE_ROOT}/raw-layouts"
RECORD_SCHEMA = "sentilab-gate-zero-record-v3"
GATE = "gate: paper-match reference, raw decoded geometry"
DEFERRED = "deferred verification: pending, no calls in this allocation"
RAW = "raw"
PAPER_MATCH_CLAIM = ("paper-match: the paper's own layout as SLAB-048 decoded it (raw continuous geometry), "
                     "reproduced within the 1.0 K prospective computational reference-reproduction tolerance")
SNAPPED_CLAIM = ("not claimed: a legal snapped variant is an engineering comparison, not the paper's layout, and "
                 "carries no paper-match claim")
PENDING = "pending verification"


class GateZeroRefusal(RuntimeError):
    """The evaluator has not passed gate zero, or its record does not bind it."""


@dataclass(frozen=True)
class Reference:
    id: str
    role: str
    paper_c: float
    source: str
    layout_identity: str                  # "raw": SLAB-048's decoded geometry; "tap-solution": a TAP-2.5D panel
    fixture: str | None = None
    raw_record: str | None = None         # SLAB-048's own record; checked whenever it is in the tree (PR #57)
    raw_vendored: str | None = None       # the frozen copy of that record's raw section, with its source commit
    raw_layout_sha256: str | None = None  # SHA-256 of the canonical JSON of the raw section (slab049.raw_layout_sha256)
    inputs: str | None = None             # frozen TAP inputs (SHA256SUMS lists them)


REFERENCES = (
    Reference("ascend910-tap25d-fig6a-raw", GATE, 75.48,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 6(a) original layout (Huawei Ascend 910); SLAB-048 raw decode",
              RAW, "ascend910", "docs/sentilab/references/ascend910-tap25d-fig6a.json",
              f"{RAW_LAYOUT_ROOT}/ascend910-tap25d-fig6a.json",
              "15c77bbeecba13a7adece9a2603329d58f33a7b4301025826c1b3c1951547a3c",
              f"{REFERENCE_ROOT}/ascend910-tap25d-fig6a-raw-45mm"),
    Reference("micro150-tap25d-fig5a-raw", GATE, 115.94,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 5(a) original placement (CPU-DRAM, Kannan et al., MICRO 2015); "
              "SLAB-048 raw decode",
              RAW, "micro150", "docs/sentilab/references/micro150-tap25d-fig5a.json",
              f"{RAW_LAYOUT_ROOT}/micro150-tap25d-fig5a.json",
              "6eba70b6307198fef85dbee0ec98055077b55e0fdae5bebb7ffe620556a457a7",
              f"{REFERENCE_ROOT}/micro150-tap25d-fig5a-raw-45mm"),
    Reference("ascend910-tap25d-fig6c", DEFERRED, 75.47,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 6(c), the TAP-2.5D solution", "tap-solution"),
    Reference("micro150-tap25d-fig5c", DEFERRED, 94.89,
              "Ma et al., TAP-2.5D, DATE 2021, Fig. 5(c), the TAP-2.5D solution with repeaterless non-pipelined links",
              "tap-solution"),
)
GATE_REFERENCES = tuple(r for r in REFERENCES if r.role == GATE)
DEFERRED_REFERENCES = tuple(r for r in REFERENCES if r.role == DEFERRED)


def reference(reference_id: str) -> Reference:
    for item in REFERENCES:
        if item.id == reference_id:
            return item
    raise GateZeroRefusal(f"{reference_id!r} is not a pinned gate-zero reference")


# The admitted call id names the role (p primary, r replay), the engine, the reference (whose id ends in its
# layout identity) and the grid, so a primary and its replay can never share an identity or an outcome.
GATE_ENGINE = "hotspot6"
ENGINE_LABELS = {"hotspot6": "hs6", "hotspot7_default": "hs7"}
ROLES = {"primary": "p", "replay": "r"}


def call_id(role: str, kind: str, reference_id: str, grid: int) -> str:
    return f"{ROLES[role]}-{ENGINE_LABELS[kind]}-{reference_id}-g{grid}"


def required_calls() -> tuple[dict, ...]:
    """The predicate's required outcomes: the native6 primary and its replay at grid 64 on every gate reference."""
    rows = []
    for item in GATE_REFERENCES:
        primary = call_id("primary", GATE_ENGINE, item.id, GRID)
        rows.append({"call": primary, "reference": item.id, "role": "primary", "replay_of": None})
        rows.append({"call": call_id("replay", GATE_ENGINE, item.id, GRID), "reference": item.id, "role": "replay",
                     "replay_of": primary})
    return tuple(rows)


PREDICATE = {
    "engine": GATE_ENGINE,
    "grid": GRID,
    "metric": METRIC,
    "tolerance_k": TOLERANCE_K,
    "tolerance_label": TOLERANCE_LABEL,
    "required": "the native6 primary call and its fresh-process replay at grid 64 on each gate reference",
    "pass": ["every required call was admitted in the grant's ledger, settled 'exited' with status 0, and its raw "
             "evidence verifies against its receipt, its ledger settlement, the frozen inputs and the manifest",
             "every required call's block-centre metric is within 1.0 K of the paper: the primary and the replay each",
             "each replay's sample.steady and sample.grid.steady are byte-identical to its primary's"],
    "fail": "a completed required call misses the tolerance, or a replay's outputs differ from its primary's",
    "incomplete": ("a required outcome is missing (never admitted), unsettled, or did not complete (any settlement "
                   "other than 'exited' with status 0): STOP. Never PASS, and not retried under this grant"),
    "deferred": "pending verification: no calls in this allocation; cannot pass or fail this gate",
    "not_judged": "the grid 32 calls and the native7 comparator are reported, never judged",
}


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_digest(item: Reference, root: Path = REPO_ROOT) -> str | None:
    return None if item.inputs is None else _sha256(root / item.inputs / "SHA256SUMS")


def references_sha256(root: Path = REPO_ROOT) -> str:
    """Digest of the pinned references, their roles, pins and frozen inputs, the predicate, the tolerance and the
    metric."""
    return hashlib.sha256(_canonical({
        "references": [{**asdict(r), "inputs_sha256sums": inputs_digest(r, root)} for r in REFERENCES],
        "predicate": PREDICATE, "required_calls": list(required_calls()),
        "claims": {"raw": PAPER_MATCH_CLAIM, "snapped": SNAPPED_CLAIM, "deferred": PENDING},
        "tolerance_k": TOLERANCE_K, "tolerance_label": TOLERANCE_LABEL, "grid": GRID,
        "interposer_mm": INTERPOSER_MM, "metric": METRIC,
    })).hexdigest()


PINNED_REFERENCES_SHA256 = "85e5b05b5ee5c0df4214226ef45db023773650274744e468d96005e27501182f"

# Evaluator kinds. Identity is checked on the bytes that are hashed: required and forbidden markers tell the
# binaries apart, so a mislabelled binary is refused. This guards against mix-ups; it does not authenticate.
# Each build writes <binary>.provenance.json (sundai_hotspot.provenance), which validate-reference requires.
VARIANT_TAG = b"SENTILAB_SINK_COUPLING=material_only;ticket=SLAB-049"
HOTSPOT6_TAG = b"SENTILAB_EVALUATOR=hotspot6@a7a3286e;grid_dump=all_layers;ticket=SLAB-049"
HOTSPOT6_COMMIT = "a7a3286e368867c26381e0a23e36b3e273bdeda9"
EVALUATOR_KINDS = {
    "hotspot7_default": {
        "binary": "sundai_hotspot/hotspot",
        "build": ("make -C sundai_hotspot -j4 SUPERLU=1 && python3 -m sundai_hotspot.provenance hotspot7_default"),
        "make": "make -C sundai_hotspot -j4 SUPERLU=1",
        "upstream": "uvahotspot/HotSpot f18831e48cef5d62580585cca0d7fab6c71bc3cc (HotSpot 7.0)",
        "required_markers": (b"microchannel",),
        "forbidden_markers": (VARIANT_TAG, b"Unit\tSteady(Kelvin)"),
    },
    "material_only": {
        "binary": "sundai_hotspot/hotspot-material-only",
        "build": "make -C sundai_hotspot SUPERLU=1 hotspot-material-only",
        "make": "make -C sundai_hotspot SUPERLU=1 hotspot-material-only",
        "upstream": "HotSpot 7.0 f18831e plus the SLAB-049 material-only spreader<->sink link (diagnostic only)",
        "required_markers": (VARIANT_TAG, b"microchannel"),
        "forbidden_markers": (b"Unit\tSteady(Kelvin)",),
    },
    "hotspot6": {
        "binary": "sundai_hotspot6/hotspot",
        "build": "bash scripts/build_hotspot6.sh",
        "make": ("make -C sundai_hotspot6 hotspot SUPERLU=1 SUPERLULIB=-lsuperlu BLASLIB=-lblas "
                 "SLU_HEADER=/usr/include/superlu EXTRAFLAGS=\"-DSENTILAB_GRID_DUMP_ALL_LAYERS=1 -ffp-contract=off\""),
        "upstream": f"uvahotspot/HotSpot {HOTSPOT6_COMMIT} (HotSpot 6.0, TAP-2.5D's version); SuperLU solver, "
                    "all-layer grid dump",
        "required_markers": (b"Unit\tSteady(Kelvin)", HOTSPOT6_TAG, b"dgssv"),
        "forbidden_markers": (b"microchannel", VARIANT_TAG),
    },
    "hotspot6_tap_faithful": {
        "binary": "sundai_hotspot6/hotspot-tap-faithful",
        "build": "bash scripts/build_hotspot6.sh",
        "make": "make -C sundai_hotspot6 hotspot SUPERLU=0 EXTRAFLAGS=\"-ffp-contract=off\" (renamed hotspot-tap-faithful)",
        "upstream": f"uvahotspot/HotSpot {HOTSPOT6_COMMIT} unmodified, SUPERLU=0 as TAP-2.5D's util/hotspot was built",
        "required_markers": (b"Unit\tSteady(Kelvin)",),
        "forbidden_markers": (b"microchannel", VARIANT_TAG, b"SENTILAB_EVALUATOR", b"dgssv"),
    },
}


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


def frozen_inputs(item: Reference, root: Path = REPO_ROOT) -> dict[str, str]:
    if item.inputs is None:
        raise GateZeroRefusal(f"{item.id}: {item.role}; it has no frozen inputs")
    sums = {}
    for line in (root / item.inputs / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest
    return sums


def _within(simulated_c: float, item: Reference) -> bool:
    return abs(simulated_c - item.paper_c) <= TOLERANCE_K


RECEIPT_SCHEMA = "sentilab-reference-validation-receipt-v3"
RECEIPT_OUTPUTS = ("stdout.txt", "stderr.txt", "sample.steady", "sample.grid.steady")
REPLAY_OUTPUTS = ("sample.steady", "sample.grid.steady")

# Every temperature here is simulated; none is measured. HotSpot 7 values carry the withdrawal notice.
TEMPERATURE_LABELS = {
    "hotspot7_default": "simulated (HotSpot 7 detailed-3D coupling; withdrawn pending the HS6 correction)",
    "material_only": ("simulated (HotSpot 7 with the SLAB-049 material-only link; bounded diagnostic evidence, "
                      "withdrawn pending the HS6 correction)"),
    "hotspot6": "simulated (HotSpot 6.0 at a7a3286e, SuperLU evaluator build)",
    "hotspot6_tap_faithful": "simulated (HotSpot 6.0 at a7a3286e, SUPERLU=0 as TAP-2.5D built it)",
}
# The grid file each build writes. Only the unmodified upstream HotSpot 6.0 build writes layer 0 alone.
GRID_FORMATS = {"hotspot7_default": "all_layers", "material_only": "all_layers", "hotspot6": "all_layers",
                "hotspot6_tap_faithful": "upstream6_top_layer"}

# A reported diagnostic, not an acceptance bound (astra #56824). HotSpot 6.0 links spreader to sink through the
# spreader's copper alone (t_sp/k_sp = 2.5e-6 m^2 K/W). The Ascend 910 compute die's 5.62e5 W/m^2 would drop at
# most 1.41 K across it even without lateral spreading. HotSpot 7's link carries half the convection resistance;
# the saved grids show about 51 K.
DROP_EXPECTATION = ("copper predicts about 1-2 K for this package (HotSpot 6.0 form); the HotSpot 7 link shows "
                    "about 51 K on the saved grids. Reported, not asserted.")


def stack_diagnostics(directory: Path) -> dict:
    """The same-index spreader-sink drop and the stack at each active-layer argmax (reads files only)."""
    from sundai_hotspot import slab049
    directory = Path(directory)
    layers = slab049.read_lcf(directory / "samplelayers.lcf", directory)
    config = slab049.read_hotspot_config(directory / "new_hotspot.config")
    ambient = float(config["ambient"])
    grid = slab049.read_grid(directory / "sample.grid.steady", ambient_k=ambient)
    if len(grid) != len(layers) + 2:
        return {"available": False, "reason": "this build writes only layer 0 to the grid file"}
    side = math.isqrt(len(grid[0]))
    return {"available": True,
            "spreader_sink_drop": slab049._same_index_drop(grid[len(layers)], grid[len(layers) + 1], side, ambient),
            "same_index_stack": slab049.same_index_stack(grid, layers, side, ambient)}


def _verify_run(kind: str, identity: dict, item: Reference, row: dict, directory: Path, manifest_sha256: str,
                root: Path) -> dict:
    """Validate one admitted call's retained run against its receipt, the manifest and the frozen inputs, and
    recompute its result from the raw outputs. Any missing or mismatched field is a refusal; nothing stored in a
    record is trusted."""
    directory = Path(directory)
    receipt_path = directory / "receipt.json"
    name = row["call"]
    if not receipt_path.is_file():
        raise GateZeroRefusal(f"{name}: no receipt in {directory}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("call") != name or receipt.get("reference") != item.id:
        raise GateZeroRefusal(f"{name}: {directory} does not hold this admitted call's receipt")
    if receipt.get("manifest_sha256") != manifest_sha256:
        raise GateZeroRefusal(f"{name}: the receipt was admitted under another manifest")
    if receipt.get("layout_identity") != RAW or receipt.get("raw_layout_sha256") != item.raw_layout_sha256:
        raise GateZeroRefusal(f"{name}: only the pinned raw layout carries the paper-match claim ({SNAPPED_CLAIM})")
    evaluator = receipt.get("evaluator") or {}
    if evaluator.get("kind") != kind or evaluator.get("binary_sha256") != identity["binary_sha256"]:
        raise GateZeroRefusal(f"{name}: the receipt was produced by a different evaluator binary")
    if receipt.get("grid") != GRID or receipt.get("status") != "exited" or receipt.get("exit_status") != 0:
        raise GateZeroRefusal(f"{name}: gate zero needs a completed grid-{GRID} solve")
    outputs = receipt.get("outputs") or {}
    for output in RECEIPT_OUTPUTS:
        if output not in outputs or not (directory / output).is_file() or _sha256(directory / output) != outputs[output]:
            raise GateZeroRefusal(f"{name}: {output} is missing or differs from its receipt digest")
    for input_name, digest in frozen_inputs(item, root).items():
        if not (directory / input_name).is_file() or _sha256(directory / input_name) != digest:
            raise GateZeroRefusal(f"{name}: {input_name} is not the frozen reference input")
        if (receipt.get("inputs") or {}).get(input_name) != digest:
            raise GateZeroRefusal(f"{name}: the receipt does not bind the frozen {input_name}")
    simulated, block = tap_selector_c(directory / "sample.steady")
    literal = None
    if kind.startswith("hotspot6"):
        literal = tap_stdout_selector_c(directory / "stdout.txt")
        if abs(literal - simulated) > 1e-9:
            raise GateZeroRefusal(f"{name}: stdout and steady-file selectors disagree")
    return {"call": name, "role": row["role"], "replay_of": row["replay_of"], "reference": item.id,
            "layout_identity": RAW, "raw_layout_sha256": item.raw_layout_sha256, "paper_c": item.paper_c,
            "simulated_c": simulated, "temperature_label": TEMPERATURE_LABELS[kind], "selector_block": block,
            "stdout_selector_c": literal, "delta_k": simulated - item.paper_c, "within_tolerance": _within(simulated, item),
            "diagnostics": stack_diagnostics(directory), "run_dir": str(directory.resolve()),
            "receipt_sha256": _sha256(receipt_path), "output_sha256": {o: outputs[o] for o in RECEIPT_OUTPUTS},
            "config_sha256": _sha256(directory / "new_hotspot.config"), "runtime": receipt.get("runtime"),
            "build_provenance_sha256": (receipt.get("build_provenance") or {}).get("sha256")}


def _ledger_entry(ledger: Path, name: str, stage: str) -> dict | None:
    path = Path(ledger) / f"{name}.{stage}.json"
    if not path.is_file():
        return None
    entry = json.loads(path.read_text(encoding="utf-8"))
    if entry.get("call") != name:
        raise GateZeroRefusal(f"{path.name} is not the {stage} ledger entry of {name}")
    return entry


def build_record(kind: str, binary: Path, ledger: Path, *, manifest_path: Path | None = None,
                 root: Path = REPO_ROOT) -> dict:
    """Gate-zero record from the grant's ledger, by admitted call id (reads files only).

    The manifest must be exactly what this tree generates. Every required call of the frozen predicate is looked up
    in the ledger; its reservation names its run directory, its settlement binds its receipt, and the receipt names
    exactly that call. So one run can never stand for two calls: a replay pointed at its primary's directory, or at
    a copy of it, is refused. The verdict is FAIL if a completed required call misses the tolerance or a replay
    differs, INCOMPLETE if any required outcome is missing, unsettled or incomplete, and PASS only when all four
    are present and hold.
    """
    from sundai_hotspot import slab049
    if kind != GATE_ENGINE:
        raise GateZeroRefusal(f"the frozen predicate judges {GATE_ENGINE} only; {kind} cannot pass this gate "
                              "(native7 is the comparator)")
    path = Path(manifest_path) if manifest_path is not None else slab049.EVIDENCE_DIR / slab049.MANIFEST_NAME
    manifest_bytes = path.read_bytes()
    try:
        manifest = slab049.check_manifest(manifest_bytes)
    except slab049.ManifestMismatch as exc:
        raise GateZeroRefusal(str(exc)) from exc
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if references_sha256(root) != PINNED_REFERENCES_SHA256:
        raise GateZeroRefusal("gate-zero references are not the pinned set")
    identity = evaluator_identity(kind, binary)
    listed = {c["id"]: c for c in manifest["calls"]}
    outcomes, missing = {}, []
    for row in required_calls():
        if row["call"] not in listed or not listed[row["call"]]["gating"]:
            raise GateZeroRefusal(f"the manifest does not list the required call {row['call']}")
        reservation = _ledger_entry(ledger, row["call"], "reserved")
        if reservation is None:
            missing.append({"call": row["call"], "reason": "not admitted: no reservation in the ledger"})
            continue
        if reservation.get("manifest_sha256") != manifest_sha256:
            raise GateZeroRefusal(f"{row['call']}: reserved under another manifest")
        settled = _ledger_entry(ledger, row["call"], "settled")
        if settled is None:
            missing.append({"call": row["call"], "reason": "unsettled: reserved but never settled"})
            continue
        if (settled.get("status"), settled.get("exit_status")) != ("exited", 0):
            missing.append({"call": row["call"], "reason": f"did not complete: settled {settled.get('status')!r}"})
            continue
        directory = Path(reservation["out"]).resolve()
        outcome = _verify_run(kind, identity, reference(row["reference"]), row, directory, manifest_sha256, root)
        if settled.get("receipt_sha256") != outcome["receipt_sha256"]:
            raise GateZeroRefusal(f"{row['call']}: the receipt changed after the call settled")
        outcomes[row["call"]] = outcome
    if len({_canonical(o["runtime"]) for o in outcomes.values()}) > 1:
        raise GateZeroRefusal("the required calls ran on different runtime library identities")
    replays = []
    for row in required_calls():
        if row["role"] == "replay" and row["call"] in outcomes and row["replay_of"] in outcomes:
            first, again = outcomes[row["replay_of"]]["output_sha256"], outcomes[row["call"]]["output_sha256"]
            replays.append({"replay": row["call"], "primary": row["replay_of"],
                            "byte_identical": all(first[name] == again[name] for name in REPLAY_OUTPUTS)})
    if any(not o["within_tolerance"] for o in outcomes.values()) or any(not r["byte_identical"] for r in replays):
        verdict = "FAIL"
    elif missing:
        verdict = "INCOMPLETE"
    else:
        verdict = "PASS"
    return {
        "schema": RECORD_SCHEMA, "verdict": verdict,
        "manifest": {"path": path.resolve().as_posix(), "sha256": manifest_sha256},
        "references_sha256": PINNED_REFERENCES_SHA256, "predicate": PREDICATE, "evaluator": identity,
        "ledger": str(Path(ledger).resolve()), "calls": outcomes, "missing": missing, "replays": replays,
        "tolerance_k": TOLERANCE_K, "tolerance_label": TOLERANCE_LABEL, "metric": METRIC,
        "temperature_label": TEMPERATURE_LABELS[kind],
        "claim_scope": {
            "paper_match": ([{"reference": r.id, "paper_c": r.paper_c, "claim": PAPER_MATCH_CLAIM}
                             for r in GATE_REFERENCES] if verdict == "PASS" else []),
            "pending_verification": [{"reference": r.id, "paper_c": r.paper_c, "source": r.source, "status": PENDING}
                                     for r in DEFERRED_REFERENCES],
            "snapped_variants": SNAPPED_CLAIM,
        },
        "pass_scope": {"evaluator_kind": kind, "binary_sha256": identity["binary_sha256"], "grid": GRID,
                       "metric": METRIC,
                       "not_covered": ("other grids, and the search objective J (the chip-layer grid peak with "
                                       "-grid_map_mode max), which is a different statistic")},
    }


def require_gate_zero(kind: str, binary: Path, record: Path | dict | None, *, grid: int = GRID,
                      root: Path = REPO_ROOT, manifest_path: Path | None = None) -> dict:
    """Refuse unless a PASS for exactly this evaluator kind, binary and grid re-derives from the record's ledger.

    The record is rebuilt from the ledger it names: every required call by id, its receipt, its settlement, its
    outputs and the frozen inputs, the metric recomputed from the steady file. A record's stored values and verdict
    are never trusted; an edited FAIL cannot unlock, and evidence that changed after the record was made is refused.
    This is integrity against edits of the record or of single files. A forger who rewrites raw outputs, receipts,
    ledger and record consistently needs the authenticated operator boundary (warden's host supervisor).

    Search and headroom call this before any evaluation. Producing the first receipts does not (reference_validation).
    """
    if record is None:
        raise GateZeroRefusal(f"{kind} has no gate-zero PASS record; search and headroom may not use it until it "
                              f"reproduces the pinned originals within the {TOLERANCE_LABEL} ({TOLERANCE_K} K)")
    data = record if isinstance(record, dict) else json.loads(Path(record).read_text(encoding="utf-8"))
    if data.get("schema") != RECORD_SCHEMA:
        raise GateZeroRefusal("gate-zero record has the wrong schema")
    if grid != GRID:
        raise GateZeroRefusal(f"a gate-zero PASS covers grid {GRID} only; grid {grid} is not covered")
    if data.get("references_sha256") != PINNED_REFERENCES_SHA256:
        raise GateZeroRefusal("gate-zero record names references other than the pinned set")
    if not data.get("ledger"):
        raise GateZeroRefusal("gate-zero record does not name its ledger")
    rebuilt = build_record(kind, binary, Path(data["ledger"]), manifest_path=manifest_path, root=root)
    if (data.get("manifest") or {}).get("sha256") != rebuilt["manifest"]["sha256"]:
        raise GateZeroRefusal("gate-zero record names another manifest")
    stored = data.get("calls") or {}
    for name, outcome in rebuilt["calls"].items():
        if (stored.get(name) or {}).get("receipt_sha256") != outcome["receipt_sha256"]:
            raise GateZeroRefusal(f"{name}: the evidence changed after the record was made")
    if rebuilt["verdict"] != "PASS":
        misses = [f"{o['call']} {o['delta_k']:+.2f} K" for o in rebuilt["calls"].values() if not o["within_tolerance"]]
        raise GateZeroRefusal(f"{kind} gate zero is {rebuilt['verdict']}: misses {misses}, missing "
                              f"{[m['call'] for m in rebuilt['missing']]}, replays {rebuilt['replays']} "
                              f"(the {TOLERANCE_LABEL} is {TOLERANCE_K} K)")
    return rebuilt
