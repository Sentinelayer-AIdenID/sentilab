"""The explicit evaluator selector (SLAB-049) and the HotSpot 6.0 oracle.

`make_oracle(evaluator, purpose)` is the one way search and headroom pick an evaluator:

- "hotspot7": the production oracle. It is unchanged: same class, same binary, same identity.
- "hotspot6": HotSpot 6.0 at uvahotspot/HotSpot a7a3286e, the version TAP-2.5D pinned, built by
  scripts/build_hotspot6.sh. It has its own solver version and problem hash.

Through this selector, every evaluator needs a gate-zero PASS for its exact binary before it can search or run
headroom (gate_zero.require_gate_zero), and a PASS covers grid 64 only: the selector refuses any other grid. The
frozen predicate judges the native6 target only, so HotSpot 7 (the comparator) cannot pass this gate and stays
locked here. The first receipts come from reference_validation validate-reference, which needs no prior PASS.

Code that constructs HotSpotOracle directly (the live loop and the existing headroom runner) is not rerouted
here. Rerouting it would stop them until HotSpot 7 passes gate zero; that is an owner decision.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

from sundai_hotspot.gate_zero import GRID, HOTSPOT6_COMMIT, GateZeroRefusal, evaluator_identity, require_gate_zero
from sundai_hotspot.tap_oracle import (
    REPO_ROOT, HotSpotOracle, HotSpotOracleError, HotSpotThermalResult, _canonical_hash,
)

EVALUATORS = {"hotspot7": "hotspot7_default", "hotspot6": "hotspot6"}
PURPOSES = ("search", "headroom")
HOTSPOT6_BINARY = REPO_ROOT / "sundai_hotspot6" / "hotspot"
EVIDENCE_PREFIX = "HotSpot 6.0 (a7a3286e) "
HOTSPOT6_SOURCES = (
    "sundai_hotspot6/UPSTREAM_COMMIT", "sundai_hotspot6/UPSTREAM_BLOBS.txt", "sundai_hotspot6/temperature_grid.c",
    "sundai_hotspot6/Makefile", "scripts/build_hotspot6.sh", "sundai_hotspot/evaluators.py",
    "sundai_hotspot/gate_zero.py",
)


def _source_hashes() -> tuple[tuple[str, str], ...]:
    return tuple((path, hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()) for path in HOTSPOT6_SOURCES)


class HotSpot6Oracle(HotSpotOracle):
    """HotSpot 6.0 behind the same TAP fixture and worker. It refuses every evaluation without a gate-zero PASS."""

    evaluator = "hotspot6"

    def __init__(self, grid_rows: int = GRID, grid_cols: int = GRID, *, hotspot_binary: Path = HOTSPOT6_BINARY,
                 gate_zero_record: Path | dict | None = None, ledger_root: Path | None = None, tags=None, **kwargs):
        binary = Path(hotspot_binary).resolve()
        try:
            identity = evaluator_identity("hotspot6", binary)
        except GateZeroRefusal as exc:
            raise HotSpotOracleError(str(exc)) from exc
        super().__init__(grid_rows, grid_cols, hotspot_binary=binary, **kwargs)
        if self.problem.hotspot_binary_sha256 != identity["binary_sha256"]:
            raise HotSpotOracleError("HotSpot 6.0 binary changed while its identity was being checked")
        sources = _source_hashes()
        self.base_problem_hash = self.problem_hash
        self.problem = replace(self.problem, hotspot_upstream_commit=HOTSPOT6_COMMIT,
                               generator_sha256=self.problem.generator_sha256 + sources)
        self.problem_hash = _canonical_hash({
            "schema": "tfl-tap-hotspot-problem-v1+evaluator-v1",
            "evaluator": self.evaluator,
            "upstream_commit": HOTSPOT6_COMMIT,
            "base_problem_hash": self.base_problem_hash,
            "evaluator_source_sha256": sources,
        })
        self.solver_version = (
            f"HotSpot-6.0:{HOTSPOT6_COMMIT}+SLAB-049:grid_dump=all_layers"
            f":binary_sha256:{self.problem.hotspot_binary_sha256}"
            f":config_sha256:{self.problem.config_sha256}"
            f":grid:{self.grid_rows}x{self.grid_cols}"
        )
        self.gate_zero = None
        self._gate_zero_refusal = None
        try:
            if self.grid_cols != self.grid_rows:
                raise GateZeroRefusal(f"a gate-zero PASS covers a {GRID} x {GRID} grid only")
            self.gate_zero = require_gate_zero(self.evaluator, binary, gate_zero_record, grid=self.grid_rows,
                                               ledger_root=ledger_root, tags=tags)
        except GateZeroRefusal as exc:
            self._gate_zero_refusal = str(exc)

    async def __call__(self, candidate, *, timeout_s: float | None = None) -> HotSpotThermalResult:
        if self.gate_zero is None:
            raise GateZeroRefusal(self._gate_zero_refusal)
        return await super().__call__(candidate, timeout_s=timeout_s)

    def _result_from_response(self, response, candidate, centers, evaluation_started) -> HotSpotThermalResult:
        result = super()._result_from_response(response, candidate, centers, evaluation_started)
        prefix = "HotSpot 7 "
        if not result.evidence_kind.startswith(prefix):  # never let a changed base label pass as HotSpot 6.0's
            raise HotSpotOracleError(f"unexpected base evidence label {result.evidence_kind!r}")
        return replace(result, evidence_kind=EVIDENCE_PREFIX + result.evidence_kind[len(prefix):])


def make_oracle(evaluator: str, purpose: str, grid_rows: int = GRID, grid_cols: int = GRID, *,
                gate_zero_record: Path | dict | None = None, ledger_root: Path | None = None, tags=None,
                **kwargs) -> HotSpotOracle:
    """Pick an evaluator for search or headroom. Refuses any evaluator without a gate-zero PASS for its binary, and
    any grid the PASS does not cover (it covers grid 64 on the block-centre metric)."""
    if evaluator not in EVALUATORS:
        raise ValueError(f"evaluator must be one of {sorted(EVALUATORS)}")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}; reference validation has its own command")
    if (grid_rows, grid_cols) != (GRID, GRID):
        raise GateZeroRefusal(f"a gate-zero PASS covers a {GRID} x {GRID} grid only, not {grid_rows} x {grid_cols}")
    if evaluator == "hotspot6":
        oracle = HotSpot6Oracle(grid_rows, grid_cols, gate_zero_record=gate_zero_record, ledger_root=ledger_root,
                                tags=tags, **kwargs)
        if oracle.gate_zero is None:
            raise GateZeroRefusal(oracle._gate_zero_refusal)
        return oracle
    oracle = HotSpotOracle(grid_rows, grid_cols, **kwargs)
    require_gate_zero(EVALUATORS[evaluator], oracle.hotspot_binary, gate_zero_record, grid=grid_rows,
                      ledger_root=ledger_root, tags=tags)
    return oracle
