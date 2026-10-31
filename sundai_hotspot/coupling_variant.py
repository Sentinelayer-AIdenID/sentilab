"""SLAB-049 CAL-COUPLING: the frozen OLD/NEW spreader<->sink coupling and the material-only evaluator.

OLD is what the vendored HotSpot 7 (upstream f18831e) assembles with ``-detailed_3D on``:
``find_res`` couples vertically adjacent cells through half of each cell's ``rz``
(temperature_grid.c, find_res detailed-3D branch), and the heatsink cell's ``rz`` already
carries its share of the convection resistance (populate_R_model_grid). So half the
convection resistance sits *between* the spreader and the sink, and the full share again
between the sink and ambient.

NEW (``coupling=material_only``) couples the spreader and sink through material
resistances only; convection stays solely on the sink-to-ambient link. Every other
conductance is unchanged. NEW is a diagnostic variant, compiled into a separate binary
(``make hotspot-material-only``) and run through its own oracle identity. The default
``hotspot`` binary, the default ``HotSpotOracle`` and every historical result are untouched.

The functions below transcribe the C expressions in the same floating-point order, so
they agree with the assembled matrix bit for bit (see test_sink_coupling.py).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path

from sundai_hotspot.tap_oracle import (
    HOTSPOT_ROOT, REPO_ROOT, HotSpotOracle, HotSpotOracleError, HotSpotThermalResult, _canonical_hash,
)

OLD = "hotspot7_default"
NEW = "material_only"
COUPLINGS = (OLD, NEW)

VARIANT_MACRO = "SENTILAB_SINK_COUPLING_MATERIAL_ONLY"
VARIANT_MAKE_TARGET = "hotspot-material-only"
VARIANT_BINARY = HOTSPOT_ROOT / VARIANT_MAKE_TARGET
# Compiled into the variant binary only (temperature_grid.c). It is an identity check against
# mixing up binaries, not an authenticity guarantee.
VARIANT_TAG = b"SENTILAB_SINK_COUPLING=material_only;ticket=SLAB-049"
# Files that define the variant. The worker re-hashes each of them before every solve.
VARIANT_SOURCES = (
    "sundai_hotspot/temperature_grid.c",
    "sundai_hotspot/Makefile",
    "sundai_hotspot/coupling_variant.py",
)
# temperature_grid.c at origin/main 3e7c480, byte-identical to upstream HotSpot f18831e.
# Removing the variant blocks from the current file must give exactly these bytes.
PRISTINE_TEMPERATURE_GRID_SHA256 = "1d50f58de5593b5620dfd26853a49f81a6ce6688218ce525b59af28b182441df"


@dataclass(frozen=True)
class PackageStack:
    """Spreader/sink parameters as HotSpot reads them (SI units)."""

    k_spreader: float  # W/(m K)
    t_spreader: float  # m
    k_sink: float      # W/(m K)
    t_sink: float      # m
    r_convec: float    # K/W for the whole sink
    s_sink: float      # m, sink edge

    @property
    def heat_transfer_coefficient(self) -> float:
        """h in W/(m^2 K): r_convec is spread over the sink area s_sink^2."""
        return 1.0 / (self.r_convec * self.s_sink * self.s_sink)

    def with_h_multiplier(self, multiplier: float) -> "PackageStack":
        return replace(self, r_convec=self.r_convec / multiplier)


@dataclass(frozen=True)
class CellResistances:
    """Per grid cell, in K/W."""

    spreader_rz: float
    sink_material_rz: float
    sink_convection_rz: float
    sink_rz: float            # populate_R_model_grid's heatsink rz: material + convection share
    spreader_sink: float      # find_res(spreader cell, sink cell)
    sink_ambient: float       # the heatsink row's link to ambient


def cell_resistances(stack: PackageStack, cell_width: float, cell_height: float, coupling: str) -> CellResistances:
    """Spreader<->sink and sink->ambient resistances of one grid cell.

    OLD:  R_sp,hs = rz_sp/2 + (rz_hs,mat + R_conv)/2      R_hs,amb = rz_hs,mat + R_conv
    NEW:  R_sp,hs = rz_sp/2 + rz_hs,mat/2                 R_hs,amb = rz_hs,mat + R_conv
    with rz = t/(k*cw*ch) and R_conv = r_convec*s_sink^2/(cw*ch).
    """
    if coupling not in COUPLINGS:
        raise ValueError(f"coupling must be one of {COUPLINGS}")
    area = cell_width * cell_height
    spreader_rz = stack.t_spreader / (stack.k_spreader * area)
    sink_material_rz = stack.t_sink / (stack.k_sink * area)
    sink_convection_rz = stack.r_convec * (stack.s_sink * stack.s_sink) / area
    sink_rz = sink_material_rz + sink_convection_rz
    if coupling == OLD:
        spreader_sink = (spreader_rz / 2.0) + (sink_rz / 2.0)
    else:
        spreader_sink = (spreader_rz / 2.0) + (sink_material_rz / 2.0)
    return CellResistances(spreader_rz, sink_material_rz, sink_convection_rz, sink_rz,
                           spreader_sink, sink_rz)


def area_resistances(stack: PackageStack, coupling: str) -> dict[str, float]:
    """The same links as specific resistances in m^2 K/W (independent of the grid)."""
    if coupling not in COUPLINGS:
        raise ValueError(f"coupling must be one of {COUPLINGS}")
    spreader = stack.t_spreader / stack.k_spreader
    sink_material = stack.t_sink / stack.k_sink
    convection = stack.r_convec * stack.s_sink * stack.s_sink
    spreader_sink = spreader / 2 + sink_material / 2 + (convection / 2 if coupling == OLD else 0.0)
    return {
        "spreader_sink": spreader_sink,
        "sink_ambient": sink_material + convection,
        "convection": convection,
        "convection_inside_interior_link": convection / 2 if coupling == OLD else 0.0,
    }


def strip_variant_blocks(source: str) -> str:
    """Return the text the default build compiles: drop each SLAB-049 block, keep its #else branch."""
    opening = f"#if {VARIANT_MACRO}"
    output = []
    state = None
    for line in source.splitlines(keepends=True):
        token = line.strip()
        if token == opening:
            if state is not None:
                raise ValueError("nested SLAB-049 variant blocks")
            state = "variant"
            continue
        if state is not None and token.startswith("#if"):
            raise ValueError("preprocessor nesting inside a SLAB-049 variant block is not supported")
        if state == "variant" and token == "#else":
            state = "default"
            continue
        if state is not None and token == "#endif":
            state = None
            continue
        if state != "variant":
            output.append(line)
    if state is not None:
        raise ValueError("unterminated SLAB-049 variant block")
    return "".join(output)


def binary_has_variant_tag(data: bytes) -> bool:
    return VARIANT_TAG in data


def variant_source_hashes(root: Path = REPO_ROOT) -> tuple[tuple[str, str], ...]:
    return tuple((path, hashlib.sha256((root / path).read_bytes()).hexdigest()) for path in VARIANT_SOURCES)


class MaterialOnlyCouplingOracle(HotSpotOracle):
    """The SLAB-049 NEW evaluator: same TAP fixture and worker, material-only spreader<->sink binary.

    Its solver version, problem hash and evidence kind all name the coupling, so a NEW result can
    never be mistaken for, or compared as, an OLD (production) result.
    """

    coupling = NEW

    def __init__(self, grid_rows: int = 32, grid_cols: int = 32, *, hotspot_binary: Path = VARIANT_BINARY, **kwargs):
        binary = Path(hotspot_binary).resolve()
        if not binary.is_file():
            raise HotSpotOracleError(f"material-only HotSpot binary is not built (make {VARIANT_MAKE_TARGET}): {binary}")
        data = binary.read_bytes()
        if not binary_has_variant_tag(data):
            raise HotSpotOracleError("binary does not carry the SLAB-049 material-only coupling tag")
        checked_sha256 = hashlib.sha256(data).hexdigest()
        super().__init__(grid_rows, grid_cols, hotspot_binary=binary, **kwargs)
        if self.problem.hotspot_binary_sha256 != checked_sha256:
            raise HotSpotOracleError("material-only binary changed while its identity was being checked")
        sources = variant_source_hashes()
        self.base_problem_hash = self.problem_hash
        self.problem = replace(self.problem, generator_sha256=self.problem.generator_sha256 + sources)
        self.problem_hash = _canonical_hash({
            "schema": "tfl-tap-hotspot-problem-v1+coupling-variant-v1",
            "ticket": "SLAB-049",
            "base_problem_hash": self.base_problem_hash,
            "coupling": self.coupling,
            "binary_tag": VARIANT_TAG.decode("ascii"),
            "variant_source_sha256": sources,
        })
        self.solver_version = (
            f"HotSpot-7:{self.problem.hotspot_upstream_commit}+SLAB-049:coupling={self.coupling}"
            f":binary_sha256:{self.problem.hotspot_binary_sha256}"
            f":config_sha256:{self.problem.config_sha256}"
            f":grid:{self.grid_rows}x{self.grid_cols}"
        )

    def _result_from_response(self, response, candidate, centers, evaluation_started) -> HotSpotThermalResult:
        result = super()._result_from_response(response, candidate, centers, evaluation_started)
        return replace(result, evidence_kind=(
            f"{result.evidence_kind}; SLAB-049 diagnostic coupling={self.coupling} (not the production oracle)"))
