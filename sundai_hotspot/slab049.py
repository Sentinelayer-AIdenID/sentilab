"""SLAB-049 CAL-COUPLING diagnostic tooling. Nothing in this module runs a thermal solve.

    python -m sundai_hotspot.slab049 analytic  [--write DIR | --check DIR]   frozen OLD/NEW links vs h,
                                                                           committed-output residuals,
                                                                           C assembly confirmation (POSIX)
    python -m sundai_hotspot.slab049 slab      [--write DIR | --check DIR]   frozen minimal-slab inputs, group (a)
    python -m sundai_hotspot.slab049 references [--write DIR | --check DIR]  frozen TAP inputs of the two raw
                                                                           paper-match references at 45 mm
    python -m sundai_hotspot.slab049 call-list [--write DIR | --check DIR]   the raw-primary manifest
                                                                           (CALL-LIST-v4.json) for the grant
    python -m sundai_hotspot.slab049 summarize EVALUATION_DIR ...           per-call record, for use after a
                                                                           granted run (reads files only)

The C harness (coupling_assembly_harness.c) builds HotSpot's grid model and assembles the conductance
matrix that direct_SLU() would factorize, then stops. It never calls the solver.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from sundai_hotspot import gate_zero
from sundai_hotspot.coupling_variant import (
    COUPLINGS, NEW, OLD, VARIANT_MACRO, PackageStack, area_resistances, cell_resistances,
)
from sundai_hotspot.tap_oracle import HOTSPOT_ROOT, REPO_ROOT, TAP_HOTSPOT_CONFIG

TICKET = "SLAB-049"
TICKET_UUID = "d41fca43-2e6c-464e-8fbc-0c485e4828dd"
# temperature_grid.c is byte-identical to upstream HotSpot f18831e at this commit (and unchanged since).
BASE_COMMIT = "3e7c4807bf2fbcf5fcde2c12659e8f35fef69f46"
EVIDENCE_DIR = REPO_ROOT / "docs" / "sentilab" / "diagnostics" / "SLAB-049"
PROBE_RESULTS = HOTSPOT_ROOT / "probe_results"
H_MULTIPLIERS = (0.5, 1.0, 2.0)
GRID_DECIMALS = 2  # dump_steady_temp_grid and dump_temp_grid print "%.2f" Kelvin
ROUNDING_K = 0.5 * 10 ** -GRID_DECIMALS
KELVIN_OFFSET = 273.15

# ----------------------------------------------------------------------------------------------
# HotSpot inputs as the TAP generator writes them
# ----------------------------------------------------------------------------------------------


def read_hotspot_config(path: Path) -> dict[str, str]:
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("-") and not parts[0].startswith("--"):
            values[parts[0][1:]] = parts[1]
    return values


def tap_package(interposer_mm: float) -> dict:
    """passive_interposer.py:154-156: spreader = 2x interposer, sink = 2x spreader, h held constant."""
    size_spreader = 2 * float(interposer_mm) / 1000
    size_heatsink = 2 * size_spreader
    r_convec = 0.1 * 0.06 * 0.06 / size_heatsink / size_heatsink
    return {"interposer_mm": float(interposer_mm), "s_spreader_m": size_spreader, "s_sink_m": size_heatsink,
            "r_convec_K_per_W": r_convec}


def tap_stack(interposer_mm: float) -> PackageStack:
    base = read_hotspot_config(TAP_HOTSPOT_CONFIG)
    package = tap_package(interposer_mm)
    return PackageStack(float(base["k_spreader"]), float(base["t_spreader"]), float(base["k_sink"]),
                        float(base["t_sink"]), package["r_convec_K_per_W"], package["s_sink_m"])


def default_h() -> float:
    """HotSpot's default sink (r_convec 0.1 K/W over 60 mm), which TAP keeps for every interposer size."""
    return 1.0 / (0.1 * 0.06 * 0.06)


# ----------------------------------------------------------------------------------------------
# Floorplans, layer files and grid outputs (readers mirror HotSpot's parsing)
# ----------------------------------------------------------------------------------------------


def read_flp(path: Path) -> list[dict]:
    units = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        unit = {"name": fields[0], "width": float(fields[1]), "height": float(fields[2]),
                "leftx": float(fields[3]), "bottomy": float(fields[4])}
        if len(fields) >= 7:
            unit["specific_heat"] = float(fields[5])
            unit["resistivity"] = float(fields[6])
        units.append(unit)
    if not units:
        raise ValueError(f"empty floorplan: {path}")
    return units


def read_lcf(path: Path, directory: Path) -> list[dict]:
    """LCF fields per layer: number, lateral, power, specific heat, resistivity, thickness, floorplan."""
    tokens = [line.split()[0] for line in Path(path).read_text(encoding="utf-8").splitlines()
              if line.split() and not line.split()[0].startswith("#")]
    if len(tokens) % 7:
        raise ValueError(f"malformed layer configuration file: {path}")
    layers = []
    for offset in range(0, len(tokens), 7):
        number, lateral, power, specific_heat, resistivity, thickness, floorplan = tokens[offset:offset + 7]
        layers.append({"layer": int(number), "lateral": lateral == "Y", "power": power == "Y",
                       "specific_heat": float(specific_heat), "resistivity": float(resistivity),
                       "thickness": float(thickness), "flp": Path(directory) / Path(floorplan.replace("\\", "/")).name})
    if [layer["layer"] for layer in layers] != list(range(len(layers))):
        raise ValueError("layer numbers must be 0..n-1 in order")
    return layers


MAX_PLAUSIBLE_K = 2273.15  # anything hotter is garbage, not a temperature


class GridFormatError(ValueError):
    """A grid steady file that is not exactly what HotSpot writes for this grid and stack."""


def read_grid(path: Path, *, grid: int | None = None, layers: int | None = None,
              ambient_k: float | None = None, headered: bool | None = None) -> dict[int, list[float]]:
    """Strictly parse a HotSpot grid steady file.

    HotSpot 7 (and the SentiLab HotSpot 6.0 evaluator build) writes "Layer n:" and then exactly grid x grid lines
    "index<TAB>T", for layers 0..L-1. Upstream HotSpot 6.0 writes layer 0 only, with no header. The reader rejects:
    duplicate or missing layers, extra, missing or out-of-order cells, a cell count that differs from grid x grid
    or between layers, and non-finite or implausible temperatures (not above 0 K, above MAX_PLAUSIBLE_K, or more
    than the print rounding below ambient, which a passive steady state cannot reach).
    """
    sections: dict[int, list[float]] = {}
    current = None
    headerless = False
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        match = re.fullmatch(r"Layer\s+(\d+):", stripped)
        if match:
            if headerless:
                raise GridFormatError(f"layer header after headerless cells at line {line_number}")
            current = int(match.group(1))
            if current in sections:
                raise GridFormatError(f"duplicate layer {current} at line {line_number}")
            sections[current] = []
            continue
        if stripped.startswith("Layer"):
            raise GridFormatError(f"malformed layer header at line {line_number}")
        if current is None:  # upstream HotSpot 6.0: the top layer only, without a header
            headerless, current = True, 0
            sections[0] = []
        fields = stripped.split()
        if len(fields) != 2:
            raise GridFormatError(f"malformed cell at line {line_number}")
        try:
            index, value = int(fields[0]), float(fields[1])
        except ValueError as exc:
            raise GridFormatError(f"malformed cell at line {line_number}") from exc
        if index != len(sections[current]):
            raise GridFormatError(f"cell index {index} out of order at line {line_number}")
        if not 0.0 < value <= MAX_PLAUSIBLE_K:  # also rejects nan and inf
            raise GridFormatError(f"implausible temperature {fields[1]} at line {line_number}")
        if ambient_k is not None and value < ambient_k - ROUNDING_K:
            raise GridFormatError(f"temperature {fields[1]} below ambient at line {line_number}")
        sections[current].append(value)
    if not sections:
        raise GridFormatError(f"no cells in {path}")
    if headered is not None and headered == headerless:
        raise GridFormatError(f"expected a {'headered all-layer' if headered else 'headerless top-layer'} grid file")
    if sorted(sections) != list(range(len(sections))):
        raise GridFormatError(f"layers {sorted(sections)} are not 0..{len(sections) - 1}")
    if layers is not None and not headerless and len(sections) != layers:
        raise GridFormatError(f"{len(sections)} layers; expected {layers}")
    counts = {len(values) for values in sections.values()}
    if len(counts) != 1:
        raise GridFormatError(f"layers differ in cell count: {sorted(counts)}")
    cells = counts.pop()
    side = math.isqrt(cells)
    if side * side != cells or (grid is not None and side != grid):
        raise GridFormatError(f"{cells} cells per layer; expected {grid if grid else 'a square'} x same")
    return sections


def grid_argmax(values: list[float], side: int) -> list[dict]:
    """Every cell holding the maximum, as (row, col); each is checked to lie inside the grid."""
    if len(values) != side * side:
        raise GridFormatError("argmax over a layer that is not grid x grid")
    peak = max(values)
    cells = [{"row": index // side, "col": index % side} for index, value in enumerate(values) if value == peak]
    for cell in cells:
        if not (0 <= cell["row"] < side and 0 <= cell["col"] < side):
            raise GridFormatError(f"argmax {cell} outside the {side} x {side} grid")
    return cells


def read_steady(path: Path) -> list[tuple[str, float]]:
    from sundai_hotspot.gate_zero import read_steady_values
    return read_steady_values(path)


def _eq(x: float, y: float) -> bool:
    return abs(x - y) < 1.0e-6  # util.c eq(), DELTA 1e-6


def _tolerant_ceil(value: float) -> int:
    nearest = math.floor(value + 0.5)
    return int(nearest) if _eq(value, nearest) else int(math.ceil(value))


def _tolerant_floor(value: float) -> int:
    nearest = math.floor(value + 0.5)
    return int(nearest) if _eq(value, nearest) else int(math.floor(value))


def total_extent(units: list[dict]) -> tuple[float, float]:
    """flp.c get_total_width / get_total_height."""
    width = max(u["leftx"] + u["width"] for u in units) - min(u["leftx"] for u in units)
    height = max(u["bottomy"] + u["height"] for u in units) - min(u["bottomy"] for u in units)
    return width, height


def block_extent(unit: dict, width: float, height: float, rows: int, cols: int) -> tuple[int, int, int, int]:
    """temperature_grid.c set_bgmap: (i1, i2, j1, j2), row 0 at the top, end indices exclusive."""
    cw, ch = width / cols, height / rows
    top = unit["bottomy"] + unit["height"]
    right = unit["leftx"] + unit["width"]
    i1 = rows - _tolerant_ceil(top / ch)
    i2 = rows - _tolerant_floor(unit["bottomy"] / ch)
    j1 = _tolerant_floor(unit["leftx"] / cw)
    j2 = _tolerant_ceil(right / cw)
    if i1 < 0 or j1 < 0 or i2 > rows or j2 > cols or i1 >= i2 or j1 >= j2:
        raise ValueError(f"block {unit['name']} does not map onto the grid")
    return i1, i2, j1, j2


def center_cells(extent: tuple[int, int, int, int]) -> list[dict]:
    """xlate_temp_g2b GRID_CENTER: the mean of four (possibly repeated) central cells, so 1, 2 or 4 cells."""
    i1, i2, j1, j2 = extent
    ci1, cj1 = (i1 + i2) // 2, (j1 + j2) // 2
    ci2 = ci1 - (1 if (i2 - i1) % 2 == 0 else 0)
    cj2 = cj1 - (1 if (j2 - j1) % 2 == 0 else 0)
    weights: dict[tuple[int, int], float] = {}
    for cell in ((ci1, cj1), (ci2, cj1), (ci1, cj2), (ci2, cj2)):
        weights[cell] = weights.get(cell, 0.0) + 0.25
    return [{"row": row, "col": col, "weight": weight} for (row, col), weight in sorted(weights.items())]


# ----------------------------------------------------------------------------------------------
# Analytic: the frozen equations as h varies
# ----------------------------------------------------------------------------------------------


def analytic_rows(grid: int = 64) -> list[dict]:
    rows = []
    for interposer in (50.0, 45.0):
        base = tap_stack(interposer)
        cell = interposer / 1000 / grid
        for multiplier in H_MULTIPLIERS:
            stack = base.with_h_multiplier(multiplier)
            for coupling in COUPLINGS:
                per_cell = cell_resistances(stack, cell, cell, coupling)
                per_area = area_resistances(stack, coupling)
                rows.append({
                    "fixture_interposer_mm": interposer,
                    "h_multiplier": multiplier,
                    "h_W_per_m2K": stack.heat_transfer_coefficient,
                    "r_convec_K_per_W": stack.r_convec,
                    "coupling": coupling,
                    "per_area_m2K_per_W": per_area,
                    "per_cell": {
                        "grid": grid,
                        "spreader_sink_K_per_W": per_cell.spreader_sink,
                        "spreader_sink_W_per_K": 1.0 / per_cell.spreader_sink,
                        "sink_ambient_K_per_W": per_cell.sink_ambient,
                        "sink_ambient_W_per_K": 1.0 / per_cell.sink_ambient,
                    },
                })
    return rows


def committed_output_residuals() -> list[dict]:
    """Node balance of interior spreader and sink cells in the committed probe outputs.

    The 2026-10-18 probe ran this HotSpot source (non-SuperLU build, which also assembles through find_res)
    and kept every layer's grid temperatures, printed to 0.01 K. Each interior cell has no power, so its
    conductance-weighted neighbour sum must vanish. The bound is what +/-0.005 K print rounding allows.
    """
    results = []
    for case in sorted(p for p in PROBE_RESULTS.iterdir() if (p / "sample.grid.steady").is_file()):
        config = read_hotspot_config(case / "new_hotspot.config")
        layers = read_lcf(case / "samplelayers.lcf", case)
        grid = read_grid(case / "sample.grid.steady")
        cells = len(grid[0])
        n = int(round(math.sqrt(cells)))
        if n * n != cells:
            raise ValueError("expected a square grid")
        width, height = total_extent(read_flp(layers[0]["flp"]))
        cw, ch = width / n, height / n
        area = cw * ch
        stack = PackageStack(float(config["k_spreader"]), float(config["t_spreader"]), float(config["k_sink"]),
                             float(config["t_sink"]), float(config["r_convec"]), float(config["s_sink"]))
        tim = len(layers) - 1
        sp, hs = tim + 1, tim + 2
        ambient = float(config["ambient"])
        tim_rz = layers[tim]["thickness"] / ((1.0 / layers[tim]["resistivity"]) * area)

        def lateral(k: float, thickness: float) -> tuple[float, float]:
            rx = cw / (k * (ch * thickness))
            ry = ch / (k * (cw * thickness))
            # find_res: neighbours in another row use rx, in another column ry (equal for square cells).
            return 1.0 / rx, 1.0 / ry

        g_sp_row, g_sp_col = lateral(stack.k_spreader, stack.t_spreader)
        g_hs_row, g_hs_col = lateral(stack.k_sink, stack.t_sink)
        record = {"case": case.name, "grid": n, "interior_cells_per_layer": (n - 2) ** 2}
        for coupling in COUPLINGS:
            links = cell_resistances(stack, cw, ch, coupling)
            g_v = 1.0 / links.spreader_sink
            g_amb = 1.0 / links.sink_ambient
            g_up = 1.0 / (tim_rz / 2.0 + links.spreader_rz / 2.0)
            worst_ratio = 0.0
            violations = 0
            residuals = []
            def t(layer: int, r: int, c: int) -> float:
                return grid[layer][r * n + c]

            for i in range(1, n - 1):
                for j in range(1, n - 1):
                    t_sp, t_hs, t_tim = t(sp, i, j), t(hs, i, j), t(tim, i, j)
                    sink = (g_v * (t_sp - t_hs) + g_hs_row * (t(hs, i - 1, j) + t(hs, i + 1, j) - 2 * t_hs)
                            + g_hs_col * (t(hs, i, j - 1) + t(hs, i, j + 1) - 2 * t_hs) + g_amb * (ambient - t_hs))
                    sink_bound = ROUNDING_K * (2 * g_v + 4 * g_hs_row + 4 * g_hs_col + g_amb)
                    spreader = (g_up * (t_tim - t_sp) + g_v * (t_hs - t_sp)
                                + g_sp_row * (t(sp, i - 1, j) + t(sp, i + 1, j) - 2 * t_sp)
                                + g_sp_col * (t(sp, i, j - 1) + t(sp, i, j + 1) - 2 * t_sp))
                    spreader_bound = ROUNDING_K * (2 * g_up + 2 * g_v + 4 * g_sp_row + 4 * g_sp_col)
                    for value, bound in ((sink, sink_bound), (spreader, spreader_bound)):
                        residuals.append(abs(value))
                        worst_ratio = max(worst_ratio, abs(value) / bound)
                        violations += abs(value) > bound
            residuals.sort()
            record[coupling] = {
                "cells_checked": len(residuals),
                "cells_outside_rounding_bound": violations,
                "worst_residual_over_bound": worst_ratio,
                "median_abs_residual_W": residuals[len(residuals) // 2],
                "max_abs_residual_W": residuals[-1],
            }
        results.append(record)
    return results


# ----------------------------------------------------------------------------------------------
# Native conductance-assembly harness (POSIX; builds HotSpot sources, never solves)
# ----------------------------------------------------------------------------------------------

COMMON_SOURCES = ("microchannel.c", "materials.c", "temperature.c", "RCutil.c", "package.c", "temperature_block.c",
                  "flp.c", "flp_desc.c", "npe.c", "shape.c", "util.c", "wire.c")
HARNESS_SOURCE = HOTSPOT_ROOT / "coupling_assembly_harness.c"
SUPERLU_INCLUDE = Path("/usr/include/superlu")
CFLAGS = ("-O3", "-DVERBOSE=1", "-DMATHACCEL=0", "-DSUPERLU=1")  # the Makefile's SUPERLU=1 flags
LIBS = ("-lm", "-lblas", "-lsuperlu")


def native_toolchain_problem() -> str | None:
    if os.name != "posix":
        return "the HotSpot sources and SuperLU build on POSIX only"
    if shutil.which("gcc") is None:
        return "gcc is not installed"
    if not (SUPERLU_INCLUDE / "slu_ddefs.h").is_file():
        return f"SuperLU headers are missing ({SUPERLU_INCLUDE})"
    return None


def _run(command: list[str], cwd: Path) -> None:
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed:\n{process.stderr[-4000:]}")


class AssemblyHarness:
    """Compiles the HotSpot objects once, then links one harness per temperature_grid.c variant."""

    def __init__(self, workdir: Path):
        problem = native_toolchain_problem()
        if problem:
            raise RuntimeError(problem)
        self.workdir = Path(workdir)
        self.common = self.workdir / "common"
        self.common.mkdir(parents=True, exist_ok=True)
        include = ["-I", str(HOTSPOT_ROOT), "-I", str(SUPERLU_INCLUDE)]
        jobs = [(["gcc", *CFLAGS, *include, "-c", str(HOTSPOT_ROOT / source), "-o",
                  str(self.common / (Path(source).stem + ".o"))], self.common) for source in COMMON_SOURCES]
        jobs.append((["gcc", *CFLAGS, *include, "-c", str(HARNESS_SOURCE), "-o", str(self.common / "harness.o")],
                     self.common))
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
            for future in [pool.submit(_run, command, cwd) for command, cwd in jobs]:
                future.result()
        self.include = include

    def build(self, label: str, grid_source: str, defines: tuple[str, ...] = ()) -> Path:
        """Compile temperature_grid.c text under its own name (objects stay comparable) and link."""
        directory = self.workdir / label
        directory.mkdir()
        (directory / "temperature_grid.c").write_bytes(grid_source.encode("utf-8"))
        _run(["gcc", *CFLAGS, *defines, *self.include, "-c", "temperature_grid.c", "-o", "temperature_grid.o"],
             directory)
        objects = [str(self.common / (Path(source).stem + ".o")) for source in COMMON_SOURCES]
        _run(["gcc", *CFLAGS, "-o", "harness", str(self.common / "harness.o"), *objects, "temperature_grid.o", *LIBS],
             directory)
        return directory / "harness"

    @staticmethod
    def run(binary: Path, inputs: Path, config: str, lcf: str, grid: int, r_convec: float,
            probe: tuple[int, int] | None = None) -> dict:
        probe = probe or (grid // 2, grid // 2)
        descriptor, name = tempfile.mkstemp(prefix="slab049-matrix-", dir=binary.parent)
        os.close(descriptor)
        matrix_path = Path(name)
        try:
            process = subprocess.run([str(binary), config, lcf, str(grid), str(grid), repr(float(r_convec)),
                                      str(probe[0]), str(probe[1]), str(matrix_path)],
                                     cwd=inputs, capture_output=True, text=True, check=False, timeout=120)
            if process.returncode != 0:
                raise RuntimeError(f"assembly harness failed: {process.stderr[-2000:]}")
            matrix = matrix_path.read_bytes()
        finally:
            matrix_path.unlink(missing_ok=True)
        return parse_harness_output(process.stdout, matrix)


def parse_harness_output(stdout: str, matrix: bytes) -> dict:
    result: dict = {"layers": {}, "vertical": {}}
    for line in stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "layers":
            result.update(n_layers=int(fields[1]), spreader=int(fields[3]), sink=int(fields[5]),
                          rows=int(fields[7]), cols=int(fields[9]))
        elif fields[0] == "cell_width":
            result.update(cell_width=float(fields[1]), cell_height=float(fields[3]))
        elif fields[0] == "r_convec":
            result.update(r_convec=float(fields[1]), s_sink=float(fields[3]), s_spreader=float(fields[5]))
        elif fields[0] == "layer":
            result["layers"][int(fields[1])] = {"k": float(fields[3]), "thickness": float(fields[5]),
                                                "rz": float(fields[7])}
        elif fields[0] == "vertical":
            result["vertical"][(int(fields[1]), int(fields[2]))] = float(fields[3])
        elif fields[0] == "sink_ambient":
            result["sink_ambient"] = float(fields[1])
    n, nnz, width = struct.unpack_from("<3i", matrix, 0)
    index_format = {4: "i", 8: "q"}[width]
    offset = 12
    colptr = struct.unpack_from(f"<{n + 1}{index_format}", matrix, offset)
    offset += (n + 1) * width
    rowind = struct.unpack_from(f"<{nnz}{index_format}", matrix, offset)
    offset += nnz * width
    values = struct.unpack_from(f"<{nnz}d", matrix, offset)
    if offset + nnz * 8 != len(matrix):
        raise ValueError("matrix dump has trailing bytes")
    result["matrix"] = {"n": n, "nnz": nnz, "colptr": colptr, "rowind": rowind, "values": values,
                        "sha256": hashlib.sha256(matrix).hexdigest(), "bytes": matrix}
    return result


def matrix_entries(matrix: dict) -> dict[tuple[int, int], float]:
    entries = {}
    for column in range(matrix["n"]):
        for position in range(matrix["colptr"][column], matrix["colptr"][column + 1]):
            entries[(matrix["rowind"][position], column)] = matrix["values"][position]
    return entries


def stage_probe_inputs(case: Path, destination: Path) -> tuple[str, str]:
    """Copy one committed TAP probe's generated inputs and point its LCF at the local floorplans."""
    destination.mkdir(parents=True, exist_ok=True)
    for path in case.iterdir():
        if path.suffix == ".flp" or path.name == "new_hotspot.config":
            shutil.copyfile(path, destination / path.name)
    lines = []
    for line in (case / "samplelayers.lcf").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        lines.append(Path(stripped).name if stripped.endswith(".flp") else line)
    (destination / "samplelayers.lcf").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "new_hotspot.config", "samplelayers.lcf"


def assembly_confirmation(workdir: Path) -> dict:
    """Run the harness on a committed TAP probe's inputs: OLD and NEW builds, three h values, grid 16."""
    harness = AssemblyHarness(workdir / "build")
    source = (HOTSPOT_ROOT / "temperature_grid.c").read_text(encoding="utf-8")
    old_binary = harness.build("old", source)
    new_binary = harness.build("new", source, (f"-D{VARIANT_MACRO}=1",))
    inputs = workdir / "inputs"
    config, lcf = stage_probe_inputs(PROBE_RESULTS / "baseline_center_32", inputs)
    base = read_hotspot_config(inputs / config)
    rows = []
    for multiplier in H_MULTIPLIERS:
        r_convec = float(base["r_convec"]) / multiplier
        for coupling, binary in ((OLD, old_binary), (NEW, new_binary)):
            run = harness.run(binary, inputs, config, lcf, 16, r_convec)
            stack = PackageStack(run["layers"][run["spreader"]]["k"], run["layers"][run["spreader"]]["thickness"],
                                 run["layers"][run["sink"]]["k"], run["layers"][run["sink"]]["thickness"],
                                 run["r_convec"], run["s_sink"])
            frozen = cell_resistances(stack, run["cell_width"], run["cell_height"], coupling)
            assembled = run["vertical"][(run["spreader"], run["sink"])]
            rows.append({
                "h_multiplier": multiplier, "coupling": coupling, "grid": 16,
                "assembled_spreader_sink_K_per_W": assembled,
                "frozen_equation_spreader_sink_K_per_W": frozen.spreader_sink,
                "bit_identical": assembled == frozen.spreader_sink,
                "assembled_sink_ambient_K_per_W": run["sink_ambient"],
                "frozen_equation_sink_ambient_K_per_W": frozen.sink_ambient,
                "interior_vertical_K_per_W": {f"{a}-{b}": value for (a, b), value in sorted(run["vertical"].items())},
                "matrix_sha256": run["matrix"]["sha256"],
            })
    gcc = subprocess.run(["gcc", "--version"], capture_output=True, text=True, check=False).stdout.splitlines()[0]
    return {"toolchain": gcc, "platform": sys.platform, "inputs": "sundai_hotspot/probe_results/baseline_center_32",
            "rows": rows}


def analytic_report(include_assembly: bool) -> dict:
    report = {
        "schema": "sentilab-slab049-analytic-v1",
        "ticket": TICKET,
        "ticket_uuid": TICKET_UUID,
        "solver_runs": 0,
        "equations": {
            OLD: "R_sp,hs = rz_sp/2 + (rz_hs,mat + R_conv)/2 ; R_hs,amb = rz_hs,mat + R_conv",
            NEW: "R_sp,hs = rz_sp/2 + rz_hs,mat/2 ; R_hs,amb = rz_hs,mat + R_conv",
            "terms": "rz = t/(k cw ch), R_conv = r_convec s_sink^2/(cw ch); per area: r_conv = 1/h",
        },
        "h_definition": "h = 1/(r_convec * s_sink^2); multipliers scale h, i.e. r_convec / multiplier",
        "frozen_equations": analytic_rows(),
        "committed_output_residuals": committed_output_residuals(),
        "committed_run1_signature": committed_run1_signature(),
    }
    if include_assembly:
        with tempfile.TemporaryDirectory(prefix="slab049-assembly-") as directory:
            report["assembly_confirmation"] = assembly_confirmation(Path(directory))
    return report


# ----------------------------------------------------------------------------------------------
# Group (a): the frozen minimal slab
# ----------------------------------------------------------------------------------------------

SLAB = {
    "description": ("one uniformly powered silicon die (TAP chip-layer material) under TAP's TIM, spreader and "
                    "sink materials; spreader and sink overhang the die by only 0.05 mm per side so the column "
                    "is one-dimensional away from the edges"),
    "die_edge_m": 0.1,
    "power_W": 1400.0,  # 1.4e5 W/m^2, TAP's 350 W over a 50 mm interposer
    "die": {"specific_heat": "1.75E+06", "resistivity": 0.01, "thickness": 0.00015},
    "tim": {"specific_heat": "4.00E+06", "resistivity": 0.25, "thickness": 2.0e-05},
    "s_spreader_m": 0.1001,
    "s_sink_m": 0.1002,
    "grid": 64,
}


def slab_r_convec(multiplier: float) -> float:
    return 1.0 / (multiplier * default_h() * SLAB["s_sink_m"] * SLAB["s_sink_m"])


def _slab_label(multiplier: float) -> str:
    return f"h{multiplier:g}".replace(".", "p")


def slab_files() -> dict[str, bytes]:
    edge = SLAB["die_edge_m"]
    header = ("# SLAB-049 minimal slab. Line Format: <unit-name>\\t<width>\\t<height>\\t<left-x>\\t<bottom-y>\n"
              "# all dimensions are in meters\n")
    files = {
        "slab_die.flp": f"{header}die\t{edge!r}\t{edge!r}\t0.0\t0.0\n",
        "slab_tim.flp": f"{header}TIM\t{edge!r}\t{edge!r}\t0.0\t0.0\n",
        "slab.lcf": ("# SLAB-049 minimal slab: layer, lateral, power, specific heat, resistivity, thickness, floorplan\n"
                     f"0\nY\nY\n{SLAB['die']['specific_heat']}\n{SLAB['die']['resistivity']!r}\n"
                     f"{SLAB['die']['thickness']!r}\nslab_die.flp\n\n"
                     f"1\nY\nN\n{SLAB['tim']['specific_heat']}\n{SLAB['tim']['resistivity']!r}\n"
                     f"{SLAB['tim']['thickness']!r}\nslab_tim.flp\n"),
        "slab.ptrace": f"die\n{SLAB['power_W']!r}\n",
    }
    template = TAP_HOTSPOT_CONFIG.read_text(encoding="utf-8")
    for multiplier in H_MULTIPLIERS:
        replacements = {
            "\t\t-s_sink\t\t\t\t0.06\n": f"\t\t-s_sink\t\t\t\t{SLAB['s_sink_m']!r}\n",
            "\t\t-s_spreader\t\t\t0.03\n": f"\t\t-s_spreader\t\t\t{SLAB['s_spreader_m']!r}\n",
            "\t\t-r_convec\t\t\t0.1\n": f"\t\t-r_convec\t\t\t{slab_r_convec(multiplier)!r}\n",
        }
        text = template
        for old, new in replacements.items():
            if text.count(old) != 1:
                raise ValueError(f"TAP hotspot.config no longer has exactly one {old.strip()!r} line")
            text = text.replace(old, new)
        files[f"slab_{_slab_label(multiplier)}.config"] = text
    return {name: content.encode("utf-8") for name, content in files.items()}


def slab_argv(binary: str, multiplier: float) -> list[str]:
    grid = str(SLAB["grid"])
    return [binary, "-c", f"slab_{_slab_label(multiplier)}.config", "-f", "slab_die.flp", "-p", "slab.ptrace",
            "-steady_file", "slab.steady", "-grid_steady_file", "slab.grid.steady", "-model_type", "grid",
            "-detailed_3D", "on", "-grid_layer_file", "slab.lcf", "-grid_rows", grid, "-grid_cols", grid,
            "-grid_map_mode", "max"]


def slab_prediction(kind: str, multiplier: float) -> dict:
    """Closed-form 1-D column at the die centre: node temperatures above ambient (K), per evaluator kind.

    HotSpot 7 (find_res): die(0)-TIM(1) = r_die + r_tim/2 (layer 0 keeps its full rz), TIM-spreader =
    r_tim/2 + r_sp/2, spreader-sink = r_sp/2 + r_hs,mat/2, plus r_conv/2 in the default build. HotSpot 6.0
    (BC_det3D): every link n -> n+1 is the upper layer's rz, so r_die, r_tim and r_sp. Sink to ambient is
    r_hs,mat + r_conv in all three. All heat leaves through the sink.
    """
    config = read_hotspot_config(TAP_HOTSPOT_CONFIG)
    stack = PackageStack(float(config["k_spreader"]), float(config["t_spreader"]), float(config["k_sink"]),
                         float(config["t_sink"]), slab_r_convec(multiplier), SLAB["s_sink_m"])
    r_die = SLAB["die"]["resistivity"] * SLAB["die"]["thickness"]
    r_tim = SLAB["tim"]["resistivity"] * SLAB["tim"]["thickness"]
    r_sp = stack.t_spreader / stack.k_spreader
    if kind == HOTSPOT6:
        die_tim, tim_spreader, spreader_sink = r_die, r_tim, r_sp
    elif kind in COUPLINGS:
        die_tim, tim_spreader = r_die + r_tim / 2, r_tim / 2 + r_sp / 2
        spreader_sink = area_resistances(stack, kind)["spreader_sink"]
    else:
        raise ValueError(f"unknown evaluator kind {kind!r}")
    sink_ambient = area_resistances(stack, OLD)["sink_ambient"]
    flux = SLAB["power_W"] / (SLAB["die_edge_m"] ** 2)
    sink = flux * sink_ambient
    spreader = sink + flux * spreader_sink
    tim = spreader + flux * tim_spreader
    die = tim + flux * die_tim
    return {"flux_W_per_m2": flux, "h_W_per_m2K": stack.heat_transfer_coefficient,
            "rise_K": {"die_layer0": die, "tim_layer1": tim, "spreader_layer2": spreader, "sink_layer3": sink},
            "interior_drop_die_minus_sink_K": die - sink,
            "observable": ("steady-file block values (-grid_map_mode max): layer_0_die, layer_1_TIM, hsp_TIM, "
                           "hsink_TIM, minus the config ambient")}


# ----------------------------------------------------------------------------------------------
# Analytic known-answer fixture (aneta #56816, astra #56833): a separate later allocation of 2 calls
# ----------------------------------------------------------------------------------------------

KNOWN_ANSWER_SLAB = {
    "id": "known-answer-slab",
    "inputs": "docs/sentilab/diagnostics/SLAB-049/slab/ (SHA256SUMS)",
    "config": "slab_h1.config",
    "argv": "slab_argv(<binary>, 1.0)",
    "allocation": "a separate later grant of 2 calls (HotSpot 6.0, HotSpot 7); not in the 12-call manifest; no "
                  "gate-zero calls",
    "observable": "the steady file's layer_0_die value (grid_map_mode max: the interior plateau) minus the ambient",
    "tolerance_rule": "max(0.5% of the expected rise, 0.02 K)",
}


def known_answer_expected(kind: str) -> dict:
    """The analytic steady rise of the full-footprint slab, from the frozen fixture files themselves.

    Geometry and power: one die layer of 100 mm x 100 mm (A = 0.01 m^2) carries P = 1400 W uniformly, so
    q = P/A = 1.4e5 W/m^2. Both chip-side floorplans cover the whole 100 x 100 mm; the grid is 64 x 64.

    Stack, in LCF order, with heat flowing toward higher indices:
      0  die       t0 = 150 um, rho0 = 0.01 m K/W
      1  TIM       t1 = 20 um,  rho1 = 0.25 m K/W
      2  spreader  t2 = 1 mm,   k2 = 400 W/(m K), s_spreader = 100.1 mm  (appended by HotSpot)
      3  sink      t3 = 6.9 mm, k3 = 400 W/(m K), s_sink = 100.2 mm      (appended by HotSpot)
    Per unit area, r_n = t_n rho_n = t_n / k_n.

    Convection: the config's r_convec (K/W for the whole sink) is applied per cell as
    R_conv,cell = r_convec * s_sink^2 / (cw * ch). Per unit area that is r_conv = r_convec * s_sink^2 = 1/h.

    Boundaries:
    - Ambient T_a = 318.15 K.
    - Adiabatic below layer 0 (model_secondary 0).
    - Every sink cell connects to ambient through its own rz.
    - The edge cells connect to the 0.05 mm package periphery, which holds 0.4% of the convective area.

    Node equations for an interior column. Uniform power makes every lateral flux vanish away from the edges.

    HotSpot 6.0. BC_det3D makes the link from n to n+1 equal rz(n):
        q = (T0 - T1)/r0 = (T1 - T2)/r1 = (T2 - T3)/r2 = (T3 - T_a)/(r3 + r_conv)
        so  T0 - T_a = q (r0 + r1 + r2 + r3 + r_conv)
    This is the physical series resistance, with convection counted once.

    HotSpot 7. find_res links half plus half, layer 0 keeps its full rz, and the sink's rz carries r_conv:
        T0 - T_a = q (r0 + r1/2 + r1/2 + r2/2 + r2/2 + (r3 + r_conv)/2 + r3 + r_conv)
                 = q (r0 + r1 + r2 + 1.5 r3 + 1.5 r_conv)

    At h x 1 (r_convec = 0.03585643085087311 K/W): r0 = 1.5e-6, r1 = 5e-6, r2 = 2.5e-6, r3 = 1.725e-5 and
    r_conv = 3.6e-4 m^2 K/W. So HotSpot 6.0 gives 54.075 K and HotSpot 7 gives 80.4825 K.

    When the slab result applies: uniform power over a single full-footprint die, near-zero overhang, no secondary
    path, steady state, and constant properties. The heterogeneous TAP package differs: partial coverage, lateral
    spreading into a 2x spreader and a 4x sink, and several dies. So the slab checks the vertical series and where
    convection sits. It does not check lateral spreading.
    """
    folder = EVIDENCE_DIR / "slab"
    layers = read_lcf(folder / "slab.lcf", folder)
    config = read_hotspot_config(folder / KNOWN_ANSWER_SLAB["config"])
    die = read_flp(layers[0]["flp"])[0]
    area = die["width"] * die["height"]
    names, values = (folder / "slab.ptrace").read_text(encoding="utf-8").split("\n")[:2]
    power = float(values.split()[names.split().index(die["name"])])
    flux = power / area
    r_die = layers[0]["resistivity"] * layers[0]["thickness"]
    r_tim = layers[1]["resistivity"] * layers[1]["thickness"]
    r_sp = float(config["t_spreader"]) / float(config["k_spreader"])
    r_hs = float(config["t_sink"]) / float(config["k_sink"])
    r_conv = float(config["r_convec"]) * float(config["s_sink"]) * float(config["s_sink"])
    if kind.startswith("hotspot6"):
        series = r_die + r_tim + r_sp + r_hs + r_conv
    elif kind == "hotspot7_default":
        series = r_die + r_tim + r_sp + 1.5 * r_hs + 1.5 * r_conv
    else:
        raise ValueError(f"no known answer is declared for {kind!r}")
    rise = flux * series
    return {"kind": kind, "flux_W_per_m2": flux, "series_m2K_per_W": series, "expected_rise_K": rise,
            "tolerance_K": max(0.005 * rise, 0.02), "ambient_K": float(config["ambient"])}


def check_known_answer_slab(run_dir: Path, kind: str) -> dict:
    """Compare a slab run's die block (steady file) with the analytic rise. Reads files only."""
    expected = known_answer_expected(kind)
    values = dict(read_steady(Path(run_dir) / "slab.steady"))
    simulated = values["layer_0_die"] - expected["ambient_K"]
    return {**expected, "simulated_rise_K": simulated, "difference_K": simulated - expected["expected_rise_K"],
            "verdict": "PASS" if abs(simulated - expected["expected_rise_K"]) <= expected["tolerance_K"] else "FAIL"}


# ----------------------------------------------------------------------------------------------
# Paper-match references: SLAB-048's raw decoded geometry and its frozen TAP inputs at 45 mm
# ----------------------------------------------------------------------------------------------

HOTSPOT6 = "hotspot6"
PAPER = "Ma et al., TAP-2.5D, DATE 2021 (HotSpot 6.0, 45 mm interposer, grid 64, 45 C ambient)"
REFERENCE_INPUTS = ("new_hotspot.config", "samplelayers.lcf", "sample.ptrace", "sampleL0_Substrate.flp",
                    "sampleL1_C4Layer.flp", "sampleL2_Interposer.flp", "sampleL3_UbumpLayer.flp",
                    "sampleL4_ChipLayer.flp", "sampleL5_TIM.flp")
_GENERATOR = r"""
import json, math, sys
from passive_interposer import PassiveInterposer
spec, out = json.loads(sys.argv[1]), sys.argv[2]
system = PassiveInterposer()
system.set_chiplet_count(len(spec["widths"]))
system.initialize()
system.set_interposer_size(spec["interposer_mm"])
system.set_chiplet_size(list(spec["widths"]), list(spec["heights"]))
system.set_chiplet_power(spec["powers"])
system.set_connection_matrix(spec["connections"])
system.set_granularity(spec["granularity"])
system.set_link_type(spec["link_type"])
system.compute_ubump_overhead()
if any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-12) for a, b in zip(system.hubump, spec["halos"])):
    sys.exit("TAP microbump halos differ from the fixture")
for index, turned in enumerate(spec["rotated"]):  # TAP's own rotate: swap the die's width and height
    if turned:
        system.rotate(index)
system.set_path(out + "/")
system.x, system.y = spec["x"], spec["y"]
system.gen_flp("sample")
system.gen_ptrace("sample")
"""
GENERATOR_CPU_LIMIT_S = 10   # RLIMIT_CPU on the TAP generator process
GENERATOR_TIMEOUT_S = 60     # its wall deadline
MARGIN_MM = 0.5              # the oracle's interposer margin, microbump halo included
MIN_DIE_GAP_MM = 0.1         # TAP-2.5D Eqn. (10): die bodies at least 0.1 mm apart
CONTINUOUS_RULES = ("continuous placement rules only: each die with its microbump halo stays 0.5 mm inside the "
                    "interposer; no two halos overlap (touching allowed); die bodies are at least 0.1 mm apart "
                    "(TAP-2.5D Eqn. (10)). No centre lattice: raw centres are continuous, and the search path's "
                    "lattice (HotSpotOracle.centers_for) is never applied to them.")


class ReferenceGeometryError(ValueError):
    """A paper-match reference's raw layout is not the pinned one, or breaks the continuous rules."""


def raw_layout_sha256(raw: dict) -> str:
    """The raw layout's own content hash: SHA-256 of its canonical JSON."""
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def load_raw_layout(reference, root: Path = REPO_ROOT) -> dict:
    """The frozen raw layout of a paper-match reference, checked against its pinned content hash.

    The vendored copy (SLAB-048 PR #57 at 063f659) must hash to the pin. Whenever SLAB-048's own record is in the
    tree, its raw section must hash to the same pin: a later SLAB-048 commit that leaves raw alone keeps the pin,
    and any change to raw fails.
    """
    document = json.loads((root / reference.raw_vendored).read_text(encoding="utf-8"))
    if raw_layout_sha256(document["raw"]) != reference.raw_layout_sha256:
        raise ReferenceGeometryError(f"{reference.id}: the frozen raw layout does not match its pinned content hash")
    record = root / reference.raw_record
    if record.is_file() and raw_layout_sha256(json.loads(record.read_text(encoding="utf-8"))["raw"]) != \
            reference.raw_layout_sha256:
        raise ReferenceGeometryError(f"{reference.id}: SLAB-048's raw section in {reference.raw_record} changed "
                                     "after it was pinned")
    return document


def _fixture_problem(fixture: str):
    from sundai_hotspot.tap_oracle import TAP_CONFIGS, _load_problem
    with tempfile.TemporaryDirectory(prefix="slab049-problem-") as directory:
        placeholder = Path(directory) / "hotspot-placeholder"
        placeholder.write_bytes(b"problem parameters only; never executed")
        return _load_problem(config_path=TAP_CONFIGS[fixture], hotspot_binary=placeholder)


def continuous_violations(footprints: list, centers: list, halos: list, size: float) -> list[str]:
    """The continuous rules (CONTINUOUS_RULES): SLAB-048's fixture rules without the centre lattice."""
    problems, rects = [], []
    for index, ((width, height), (x, y), halo) in enumerate(zip(footprints, centers, halos)):
        rect = (x - width / 2 - halo, y - height / 2 - halo, x + width / 2 + halo, y + height / 2 + halo)
        if (rect[0] < MARGIN_MM - 1e-9 or rect[1] < MARGIN_MM - 1e-9 or rect[2] > size - MARGIN_MM + 1e-9
                or rect[3] > size - MARGIN_MM + 1e-9):
            problems.append(f"die {index} with its halo breaks the {MARGIN_MM} mm margin")
        rects.append(rect)
    for i, a in enumerate(rects):
        for j, b in enumerate(rects[:i]):
            if not (a[2] <= b[0] + 1e-9 or b[2] <= a[0] + 1e-9 or a[3] <= b[1] + 1e-9 or b[3] <= a[1] + 1e-9):
                problems.append(f"dies {j} and {i} overlap with their halos")
    bodies = [(r[0] + h, r[1] + h, r[2] - h, r[3] - h) for r, h in zip(rects, halos)]
    for i, a in enumerate(bodies):
        for j, b in enumerate(bodies[:i]):
            gap = max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3])
            if gap < MIN_DIE_GAP_MM - 1e-9:
                problems.append(f"dies {j} and {i} are {gap:.4f} mm apart, under the {MIN_DIE_GAP_MM} mm spacing")
    return problems


def spec_from_raw_layout(document: dict, fixture: str) -> dict:
    """TAP generator inputs for a raw layout, after checking it against the fixture and the continuous rules."""
    problem = _fixture_problem(fixture)
    raw = document["raw"]
    size = float(document["interposer_mm"])
    count = len(problem.widths_mm)
    rotated = list(raw["rotated"])
    centers = [[float(x), float(y)] for x, y in raw["centers_mm"]]
    if not (len(rotated) == len(centers) == len(document["dies"]) == len(raw["footprints_mm"]) == count):
        raise ReferenceGeometryError("the raw layout does not give one entry per fixture die")
    if any(not isinstance(flag, bool) for flag in rotated):
        raise ReferenceGeometryError("every rotation flag must be a boolean")
    catalog = list(zip(problem.widths_mm, problem.heights_mm))
    for index, (die, (width, height), power, halo) in enumerate(
            zip(document["dies"], catalog, problem.powers_w, problem.bump_halos_mm)):
        if (not (math.isclose(die["catalog_mm"][0], width, abs_tol=1e-12) and
                 math.isclose(die["catalog_mm"][1], height, abs_tol=1e-12)) or
                not math.isclose(die["power_w"], power, abs_tol=1e-12) or
                not math.isclose(die["halo_mm"], halo, abs_tol=1e-12)):
            raise ReferenceGeometryError(f"die {index}: SLAB-048's catalog size, power or halo is not the fixture's")
    footprints = [(height, width) if turned else (width, height) for (width, height), turned in zip(catalog, rotated)]
    for index, (footprint, decoded) in enumerate(zip(footprints, raw["footprints_mm"])):
        if not all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(footprint, decoded)):
            raise ReferenceGeometryError(f"die {index}: the raw footprint is not the catalog die turned as flagged")
    halos = list(problem.bump_halos_mm)
    problems = continuous_violations(footprints, centers, halos, size)
    if problems:
        raise ReferenceGeometryError(f"the raw layout breaks the continuous rules: {problems}")
    return {"interposer_mm": size, "widths": [w for w, _ in catalog], "heights": [h for _, h in catalog],
            "rotated": rotated, "powers": list(problem.powers_w), "connections": [list(r) for r in problem.connections],
            "granularity": problem.granularity_mm, "link_type": problem.link_type, "halos": halos,
            "x": [c[0] for c in centers], "y": [c[1] for c in centers],
            "geometry": {"rules": CONTINUOUS_RULES, "search_lattice_checked": False, "violations": []}}


def reference_spec(reference_id: str, root: Path = REPO_ROOT) -> dict:
    """The pinned raw layout of a gate reference as TAP generator inputs (continuous rules only)."""
    reference = gate_zero.reference(reference_id)
    if reference.layout_identity != gate_zero.RAW or reference.inputs is None:
        raise ReferenceGeometryError(f"{reference_id} has no frozen raw layout ({reference.role})")
    return spec_from_raw_layout(load_raw_layout(reference, root), reference.fixture)


def _cpu_limit(seconds: int):
    def apply() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    return apply


def generate_reference(spec: dict, directory: Path) -> dict[str, bytes]:
    """Run TAP's own generator for `spec` in `directory`; return the HotSpot inputs with a local, LF-only LCF."""
    from sundai_hotspot.tap_oracle import TAP_ROOT
    limit = {"preexec_fn": _cpu_limit(GENERATOR_CPU_LIMIT_S)} if os.name == "posix" else {}
    process = subprocess.run([sys.executable, "-c", _GENERATOR, json.dumps(spec), str(directory)], cwd=TAP_ROOT,
                             capture_output=True, text=True, check=False, timeout=GENERATOR_TIMEOUT_S, **limit)
    if process.returncode != 0:
        raise RuntimeError(f"TAP generator failed: {process.stderr[-2000:]}")
    # TAP writes in text mode; keep the Linux bytes (LF) the run host produces, whatever generated them.
    files = {name: (Path(directory) / name).read_bytes().replace(b"\r\n", b"\n") for name in REFERENCE_INPUTS}
    lines = []
    for line in files["samplelayers.lcf"].decode("utf-8").splitlines():
        stripped = line.strip()
        lines.append(Path(stripped.replace("\\", "/")).name if stripped.endswith(".flp") else line)
    files["samplelayers.lcf"] = ("\n".join(lines) + "\n").encode("utf-8")
    return files


def reference_files(reference_id: str) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="slab049-reference-") as directory:
        return generate_reference(reference_spec(reference_id), Path(directory))


def tap_argv(binary: str, grid: int = 64) -> list[str]:
    """TAP-2.5D's run_hotspot command (passive_interposer.py:197-206); grid 64 and center mapping come from the
    config. Other grids override rows and columns only."""
    argv = [binary, "-c", "new_hotspot.config", "-f", "sampleL4_ChipLayer.flp", "-p", "sample.ptrace",
            "-steady_file", "sample.steady", "-grid_steady_file", "sample.grid.steady", "-model_type", "grid",
            "-detailed_3D", "on", "-grid_layer_file", "samplelayers.lcf"]
    return argv if grid == 64 else argv + ["-grid_rows", str(grid), "-grid_cols", str(grid)]


# The v7 signature: rise above ambient (K) at the hottest spreader and sink cells, Ascend 910 at 45 mm, from
# aneta-claude's independent network model (#56739, not HotSpot). Recorded for every solve; the cause is settled.
RUN1_SIGNATURES_ASCEND_45MM = {
    "correct (HotSpot 6 form, the paper's)": [26.5, 25.2],
    "v7 spreader-sink link": [73.5, 19.2],
    "r_convec not rescaled": [62.4, 61.2],
}


def run1_pattern(spreader_rise: float, sink_rise: float) -> dict:
    ratio = (spreader_rise - sink_rise) / sink_rise
    pattern = "v7-link" if ratio >= 1.0 else ("v6-like" if ratio <= 0.25 else "ambiguous")
    distances = {name: math.hypot(spreader_rise - s, sink_rise - k)
                 for name, (s, k) in RUN1_SIGNATURES_ASCEND_45MM.items()}
    return {"spreader_rise_K": spreader_rise, "sink_rise_K": sink_rise, "drop_over_sink_rise": ratio,
            "pattern": pattern, "distance_to_ascend_45mm_signatures_K": distances}


def committed_run1_signature() -> list[dict]:
    """The spreader and sink reading on the committed 2026-10-18 probe outputs (50 mm, probe layouts, grids 16/32)."""
    records = []
    for case in sorted(p for p in PROBE_RESULTS.iterdir() if (p / "sample.grid.steady").is_file()):
        config = read_hotspot_config(case / "new_hotspot.config")
        layers = read_lcf(case / "samplelayers.lcf", case)
        ambient = float(config["ambient"])
        grid = read_grid(case / "sample.grid.steady", layers=len(layers) + 2, ambient_k=ambient)
        records.append({"case": case.name, "r_convec": config["r_convec"], "s_sink": config["s_sink"],
                        "s_spreader": config["s_spreader"],
                        "r_convec_is_generator_scaled": float(config["r_convec"]) == tap_package(50)["r_convec_K_per_W"],
                        **run1_pattern(max(grid[len(layers)]) - ambient, max(grid[len(layers) + 1]) - ambient)})
    return records


# ----------------------------------------------------------------------------------------------
# The manifest: one frozen list of 12 calls on the two raw references (root #56858; astra, PR #56 6545712065)
# ----------------------------------------------------------------------------------------------

MANIFEST_NAME = "CALL-LIST-v4.json"
MANIFEST_SCHEMA = "sentilab-slab049-manifest-v4"
# The snapped-primary manifest astra and warden reviewed at 6413a3c stays in the tree byte-identical, as an
# artifact. validate-reference never reads it.
PRIOR_MANIFEST = {
    "path": "docs/sentilab/diagnostics/SLAB-049/CALL-LIST.json",
    "schema": "sentilab-slab049-manifest-v3",
    "sha256": "952c23845599b5536c08a31d9fe77c58556d803c8d3553d568e9099df9c35973",
    "description": "docs/sentilab/diagnostics/SLAB-049/CALL-LIST.md",
    "description_sha256": "e2f94ca55482f47f48437b4f84a3369fe7643324c25da80c0058c4c94cc9d665",
    "reviewed_head": "6413a3c0cc2b6280dc2bf063812374e0c8d3d337",
    "status": ("prior artifact, kept byte-identical: the snapped-primary manifest as reviewed at 6413a3c; "
               "superseded by the raw-primary choice and refused by validate-reference"),
}
SUCCESSOR_REASON = ("root #56858 and forge reply 1ed1c902 ('gate zero unchanged: 8+4 on the two raw45mm references'): "
                    "the paper-match comparison uses SLAB-048's raw decoded geometry, and snapped variants are a "
                    "separate engineering comparison. The allocation stays exactly 12 calls.")
SLAB048_COMMIT = "063f659368f32b653acf8084f85a0c7926a106ec"
MANIFEST_ENGINES = (("hs6", HOTSPOT6, "native6 target"), ("hs7", "hotspot7_default", "native7 comparator"))
SUPERVISOR_POLICY = "docs/sentilab/evidence/SLAB-039/SUPERVISOR-POLICY.json"
TIMING = {  # micro150/TIMING.json, Azure x86_64 (16 CPU); HotSpot 6.0 SuperLU is unmeasured and assumed alike
    "grid64_expected_wall_s": 4.76,
    "grid32_expected_wall_s": 0.49,
    "grid64_timeout_s": 60.0,
    "grid32_timeout_s": 15.0,
    "per_call_overhead_cpu_s": 1.5,  # forecast: TAP generation, hashing, library hashing, staging, record
}
MANIFEST_CPU_CAP_S = 600.0    # this manifest's cap, 10 CPU-min since 6413a3c: the tighter one, it binds
ROOM_ENVELOPE_CPU_S = 1800.0  # the room's earlier prospective envelope, 30 CPU-min: looser, it does not bind
MANIFEST_SOURCES = (
    "scripts/build_hotspot6.sh", "sundai_hotspot/Makefile", "sundai_hotspot/temperature_grid.c",
    "sundai_hotspot/tap_oracle.py", "sundai_hotspot/tap_oracle_worker.py", "sundai_hotspot/gate_zero.py",
    "sundai_hotspot/evaluators.py", "sundai_hotspot/reference_validation.py", "sundai_hotspot/slab049.py",
    "sundai_hotspot/provenance.py", "sundai_hotspot6/UPSTREAM_COMMIT", "sundai_hotspot6/UPSTREAM_BLOBS.txt",
    "sundai_hotspot6/temperature_grid.c", "sundai_hotspot6/Makefile", "sundai_tap/passive_interposer.py",
    "sundai_tap/system.py", "sundai_tap/util/hotspot.config", "sundai_tap/util/fill_space.py",
    "sundai_tap/configs/sys_ascend910.cfg", "sundai_tap/configs/sys_micro150.cfg",
    "docs/sentilab/diagnostics/SLAB-049/references/raw-layouts/ascend910-tap25d-fig6a.json",
    "docs/sentilab/diagnostics/SLAB-049/references/raw-layouts/micro150-tap25d-fig5a.json",
    SUPERVISOR_POLICY,
)
PURPOSES = {
    (HOTSPOT6, "primary", 64): "gate zero: the block-centre metric within 1.0 K of the paper (native6 target)",
    (HOTSPOT6, "replay", 64): ("gate zero: fresh-process replay of the native6 primary; byte-identical outputs and "
                               "within 1.0 K on its own"),
    (HOTSPOT6, "primary", 32): "reported, not judged: HotSpot 6.0 at grid 32 against grid 64",
    ("hotspot7_default", "primary", 64): ("reported, not judged: native7 comparator at the paper's grid (simulated; "
                                          "withdrawn pending the HS6 correction)"),
    ("hotspot7_default", "replay", 64): "reported, not judged: native7 comparator replay (byte identity)",
    ("hotspot7_default", "primary", 32): "reported, not judged: native7 comparator at grid 32 against grid 64",
}
IN_CODE_AT_ENTRY = (
    "manifest identity: validate-reference reads only CALL-LIST-v4.json and refuses it unless it is byte-identical "
    "to what this tree generates (every source pin, reference input, raw layout hash, the predicate and the "
    "accounting); the prior snapped manifest is refused",
    "listed calls only: the call id with its listed --timeout, and the engine, reference and grid when given; "
    "before the window closes; on the listed architecture; on POSIX only, because the CPU limit is RLIMIT_CPU "
    "(Linux and macOS; Windows has no RLIMIT_CPU, and its equivalent, a Job Object process-time limit, is not "
    "implemented, so the entry refuses there)",
    "evaluator identity: identity markers and SHA-256 are read from a private content-addressed copy (mode 0500 in a "
    "0700 directory), and that copy is the file executed; build provenance must describe exactly those bytes; the "
    "shared libraries the loader resolves must equal the build's, and are hashed again after the run (a change "
    "settles the call as runtime_changed)",
    "raw geometry: the pinned raw layout hash (the vendored copy, and SLAB-048's record whenever it is in the tree) "
    "and the continuous rules only; the search lattice is never applied",
    "atomic admission: under an exclusive ledger lock, one manifest per ledger, each call reserved once (O_EXCL, no "
    "retries), refused when the admitted count would pass 12 or charged plus reserved CPU would pass 600 CPU-s "
    "(settled calls are charged their measured CPU, unsettled ones their reservation)",
    "reserve before staging: the reservation and the receipt are on disk (fsync) before inputs are generated or the "
    "solver starts",
    "per-process CPU and a separate wall deadline: the solver runs in its own session and process group under "
    "RLIMIT_CPU equal to its timeout (soft = hard, so SIGKILL at the limit) and a wall deadline equal to its "
    "timeout; the TAP generator runs under RLIMIT_CPU 10 s and a 60 s deadline",
    "kill and reap: after the solver exits or times out, its process group is killed and the solver is reaped",
    "settlement: the receipt and the ledger settlement are written durably on every exit path of this process, "
    "keeping the raw outputs, the status, the measured CPU (children and self) and any overshoot",
    "outcomes by admitted call id: record and report read the ledger, never caller-chosen directories; a missing "
    "required outcome gives INCOMPLETE",
)
SUPERVISOR_CONTRACT = (
    "admission identity: authenticate the operator and the host; keep the ledger append-only and protected from "
    "deletion or rewrite (deleting a reservation would readmit its call); one ledger per grant",
    "a cumulative CPU budget over the whole process group, descendants and lifecycle work included, enforced while "
    "calls run (for example a cgroup v2 budget that kills at the limit); in code, RLIMIT_CPU is per process and the "
    "ledger's cumulative check acts at admission only",
    "kill and reap if validate-reference itself dies (SIGKILL, OOM, host loss): settle the call as unknown, charge "
    "its reservation, and never let it become a free replacement",
    "a protected runtime image: run the loader and libraries from immutable copies; in code, the executable is a "
    "private copy, but libraries are hashed before and after the run, which cannot detect a swap-and-restore "
    "during it",
    "a trusted clock for the grant window; the code reads the host clock",
    "the final grant reconciles the 600 CPU-s manifest cap with the room's 1,800 CPU-s envelope; neither is raised "
    "here",
)


class ManifestMismatch(ValueError):
    """A manifest that is not exactly the one this tree generates."""


def _file_sha256(path: str) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()


def _sums_digest(directory: str) -> str:
    return _file_sha256(f"{directory}/SHA256SUMS")


def _policy_reserves() -> dict:
    limits = json.loads((REPO_ROOT / SUPERVISOR_POLICY).read_text(encoding="utf-8"))["limits"]
    return {"reap_s": float(limits["reap_seconds"]), "settlement_tail_s": float(limits["settlement_tail_cpu_seconds"])}


def per_call_reserve_s() -> float:
    """The overhead assumption per call: the generation-hashing-record forecast plus SLAB-039's reap and tail."""
    reserves = _policy_reserves()
    return TIMING["per_call_overhead_cpu_s"] + reserves["reap_s"] + reserves["settlement_tail_s"]


def _manifest_call(role: str, engine: str, kind: str, engine_role: str, reference, grid: int,
                   replay_of: str | None = None) -> dict:
    name = gate_zero.call_id(role, kind, reference.id, grid)
    timeout = TIMING[f"grid{grid}_timeout_s"]
    binary = gate_zero.EVALUATOR_KINDS[kind]["binary"]
    return {
        "id": name, "role": role, "replay_of": replay_of, "engine": engine, "engine_role": engine_role, "kind": kind,
        "binary": binary, "reference": reference.id, "layout_identity": reference.layout_identity,
        "raw_layout_sha256": reference.raw_layout_sha256, "paper_peak_c": reference.paper_c, "grid": grid,
        "gating": kind == gate_zero.GATE_ENGINE and grid == gate_zero.GRID, "purpose": PURPOSES[(kind, role, grid)],
        "inputs": {"dir": reference.inputs, "sha256sums_sha256": _sums_digest(reference.inputs)},
        "timeout_s": timeout, "cpu_limit_s": math.ceil(timeout),
        "command": (f"python -m sundai_hotspot.reference_validation validate-reference --call {name} "
                    f"--timeout {timeout:g} --out <fresh empty dir> --ledger <the grant's ledger dir>"),
        "argv": tap_argv(f"<private content-addressed copy of {binary}>", grid),
        "accounting": {"expected_cpu_s": round(TIMING[f"grid{grid}_expected_wall_s"] +
                                               TIMING["per_call_overhead_cpu_s"], 2),
                       "reserved_cpu_s": timeout + per_call_reserve_s()},
    }


def build_call_list() -> dict:
    references = gate_zero.GATE_REFERENCES
    calls = [_manifest_call("primary", engine, kind, role, reference, grid)
             for engine, kind, role in MANIFEST_ENGINES for reference in references for grid in (64, 32)]
    calls += [_manifest_call("replay", engine, kind, role, reference, 64,
                             replay_of=gate_zero.call_id("primary", kind, reference.id, 64))
              for engine, kind, role in MANIFEST_ENGINES for reference in references]
    if len({c["id"] for c in calls}) != len(calls):
        raise ValueError("call ids must be unique")
    if sorted(row["call"] for row in gate_zero.required_calls()) != sorted(c["id"] for c in calls if c["gating"]):
        raise ValueError("the gating rows must be exactly the predicate's required calls")
    reserves, per_call = _policy_reserves(), per_call_reserve_s()
    grid64, grid32 = sum(c["grid"] == 64 for c in calls), sum(c["grid"] == 32 for c in calls)
    timeouts = sum(c["timeout_s"] for c in calls)
    forecast = timeouts + per_call * len(calls)
    if forecast > MANIFEST_CPU_CAP_S:  # warden #56856: generation fails when the worst case leaves the cap
        raise ValueError(f"the forecast worst case, {forecast:g} CPU-s, exceeds the manifest cap of "
                         f"{MANIFEST_CPU_CAP_S:g} CPU-s")
    arithmetic = (f"{grid64} x {TIMING['grid64_timeout_s']:g} s + {grid32} x {TIMING['grid32_timeout_s']:g} s = "
                  f"{timeouts:g} s of timeouts, plus {len(calls)} x {per_call:g} CPU-s = {per_call * len(calls):g} "
                  f"CPU-s of overhead assumption ({TIMING['per_call_overhead_cpu_s']:g} generation, hashing and record; "
                  f"{reserves['reap_s']:g} reap and {reserves['settlement_tail_s']:g} settlement tail from "
                  f"SLAB-039's SUPERVISOR-POLICY.json) = {forecast:g} CPU-s")
    kinds = (HOTSPOT6, "hotspot7_default")
    return {
        "schema": MANIFEST_SCHEMA,
        "ticket": TICKET,
        "ticket_uuid": TICKET_UUID,
        "status": ("PROPOSED. The raw-primary manifest: 12 calls on the two raw 45 mm references, for warden's grant "
                   "against the merged build. Nothing has been executed; no solve has been run for SLAB-049."),
        "generated_by": "python -m sundai_hotspot.slab049 call-list --write docs/sentilab/diagnostics/SLAB-049",
        "paper": PAPER,
        "supersedes": {**PRIOR_MANIFEST, "reason": SUCCESSOR_REASON},
        "allocation": ("exactly 12 calls: 2 raw 45 mm references x {native6 target, native7 comparator} x grids "
                       "{64, 32}, plus one fresh-process grid-64 replay per reference and engine. Native7 is a "
                       "comparator, not required to reproduce the native6 targets. The deferred verification points "
                       "add no call."),
        "grant_window": {"not_before": "warden's grant against the merged build",
                         "not_after_utc": "2026-11-01T12:00:00Z",
                         "per_call_receipts_record": "effective start and stop (UTC), wall and CPU seconds"},
        "source": {"pin": ("SHA-256 of every file that builds, stages or judges the calls; validate-reference refuses "
                           "a manifest that is not exactly what the tree generates"),
                   "files_sha256": {path: _file_sha256(path) for path in MANIFEST_SOURCES}},
        "builds": {
            kind: {"command": gate_zero.EVALUATOR_KINDS[kind]["build"], "make": gate_zero.EVALUATOR_KINDS[kind]["make"],
                   "binary": gate_zero.EVALUATOR_KINDS[kind]["binary"],
                   "provenance": gate_zero.EVALUATOR_KINDS[kind]["binary"] + ".provenance.json",
                   "upstream": gate_zero.EVALUATOR_KINDS[kind]["upstream"],
                   "binary_sha256": "recorded by the build in its provenance file; every receipt binds it",
                   "identity_markers": {
                       "required": [m.decode("ascii") for m in gate_zero.EVALUATOR_KINDS[kind]["required_markers"]],
                       "forbidden": [m.decode("ascii") for m in gate_zero.EVALUATOR_KINDS[kind]["forbidden_markers"]]}}
            for kind in kinds},
        "references": {
            r.id: {"role": r.role, "layout_identity": r.layout_identity, "paper_peak_c": r.paper_c, "source": r.source,
                   "claim": gate_zero.PAPER_MATCH_CLAIM,
                   "raw_layout": {"sha256": r.raw_layout_sha256,
                                  "form": "SHA-256 of the canonical JSON of SLAB-048's raw section "
                                          "(slab049.raw_layout_sha256)",
                                  "vendored": r.raw_vendored, "slab048_record": r.raw_record,
                                  "slab048_pull_request": 57, "slab048_commit": SLAB048_COMMIT},
                   "geometry_rules": CONTINUOUS_RULES,
                   "inputs": {"dir": r.inputs, "sha256sums_sha256": _sums_digest(r.inputs)}}
            for r in references},
        "deferred": {r.id: {"role": r.role, "paper_peak_c": r.paper_c, "source": r.source,
                            "status": gate_zero.PENDING, "calls": 0} for r in gate_zero.DEFERRED_REFERENCES},
        "snapped_variants": (gate_zero.SNAPPED_CLAIM + ". SLAB-048's 0.5 mm variants are a separate "
                             "engineering-comparison allocation with their own identities."),
        "gate_zero": {"module": "sundai_hotspot/gate_zero.py", "tolerance_k": gate_zero.TOLERANCE_K,
                      "tolerance_label": gate_zero.TOLERANCE_LABEL,
                      "pinned_references_sha256": gate_zero.PINNED_REFERENCES_SHA256,
                      "predicate": gate_zero.PREDICATE, "required_calls": list(gate_zero.required_calls())},
        "calls": calls,
        "accounting": {
            "calls": len(calls), "grid64_calls": grid64, "grid32_calls": grid32, "max_runs": len(calls), "retries": 0,
            "timing_basis": TIMING, "policy_reserves": reserves, "per_call_reserve_cpu_s": per_call,
            "timeouts_s": timeouts,
            "arithmetic": arithmetic,
            "forecast_worst_case_cpu_s": forecast,
            "forecast_label": ("a forecast under declared assumptions, not a CPU guarantee: RLIMIT_CPU bounds each "
                               "solver process at its timeout and the generator at 10 CPU-s; the parent's own work "
                               "and any unreaped descendants are measured, not capped; the hard cumulative "
                               "process-group cap is the supervisor's"),
            "expected_cpu_s": round(sum(c["accounting"]["expected_cpu_s"] for c in calls), 2),
            "manifest_cpu_cap_s": MANIFEST_CPU_CAP_S,
            "room_envelope_cpu_s": ROOM_ENVELOPE_CPU_S,
            "binding_cap": ("the manifest cap, 600 CPU-s, binds: it is the tighter of the two. The room's 1,800 CPU-s "
                            "prospective envelope does not bind. Neither is raised here; the final grant reconciles "
                            "them."),
            "concurrency": 1, "gpu": False,
            "host": "x86_64 Azure host behind the mesh and TIMING evidence; an aarch64 build needs its own receipts",
            "host_architecture": "x86_64",
        },
        "enforcement": {"in_code_at_entry": list(IN_CODE_AT_ENTRY),
                        "operator_supervisor_contract": list(SUPERVISOR_CONTRACT)},
        "next_allocation": [
            "the deferred verification points, pending: Ascend 910 Fig. 6(c) at 75.47 C and CPU-DRAM Fig. 5(c) at "
            "94.89 C (SLAB-048 validation_points), with their own calls",
            "HotSpot 6.0 built SUPERLU=0 exactly as TAP-2.5D's util/hotspot (kind hotspot6_tap_faithful) on both raw "
            "originals: the solver cross-check",
            "the aarch64 (GB10) build's own gate-zero receipts",
            "SLAB-048's 0.5 mm legal snapped variants, as an engineering comparison that never carries the "
            "paper-match claim",
            "a 50 mm frame comparison and NEW-evaluator mesh margins",
        ],
        "separate_allocations": [
            {**KNOWN_ANSWER_SLAB, "calls": 2, "engines": [HOTSPOT6, "hotspot7_default"],
             "in_this_manifest": False, "gate_zero_calls": False,
             "expected_rise_K": {kind: known_answer_expected(kind)["expected_rise_K"] for kind in kinds},
             "equations": "slab049.known_answer_expected docstring: geometry, power, area, node and boundary "
                          "equations, the series-resistance derivation, and when the slab result applies"},
            {"id": "24-layout re-score study", "in_this_manifest": False,
             "note": "a later separate allocation; not folded into this manifest"},
        ],
        "post_run_diagnostics": ("From the 12 calls, with no extra call (reference_validation report, by call id from "
                                 "the ledger): HotSpot 6.0's grid 32 -> 64 change per reference (aneta's network model "
                                 "predicts 0.01 K Ascend, 0.18 K CPU-DRAM; the old HotSpot 7 micro150 mesh error was "
                                 "0.79 K), CPU-s per call, replay byte identity, the same-index spreader-sink drop and "
                                 "the same-index stack at each active-layer argmax (reported, not asserted). Nothing "
                                 "is frozen on them or on the old mesh error."),
        "not_requested": ("The prior snapped-primary rows; the v1 and v2 plans (32 calls, 37 executions; later 23); "
                          "and every material-only HotSpot 7 call. The material-only flag stays as labelled, bounded "
                          "diagnostic evidence; it is not the MATCH evaluator and inherits no grant."),
    }


def check_manifest(manifest_bytes: bytes) -> dict:
    """The manifest, if and only if it is byte-identical to the one this tree generates. Otherwise a refusal that
    names what differs: a source pin, a reference input, the predicate or a row."""
    if hashlib.sha256(manifest_bytes).hexdigest() == PRIOR_MANIFEST["sha256"]:
        raise ManifestMismatch("the prior snapped manifest (CALL-LIST.json, as reviewed at 6413a3c) is an artifact, "
                               "not an executable manifest")
    try:
        manifest = json.loads(manifest_bytes)
    except ValueError as exc:
        raise ManifestMismatch(f"the manifest is not JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ManifestMismatch(f"not a {MANIFEST_SCHEMA} manifest")
    fresh = _dump(build_call_list())
    if manifest_bytes == fresh:
        return manifest
    regenerated = json.loads(fresh)
    pins, current = manifest.get("source", {}).get("files_sha256", {}), regenerated["source"]["files_sha256"]
    drift = sorted(path for path in set(pins) | set(current) if pins.get(path) != current.get(path))
    sections = sorted(key for key in set(manifest) | set(regenerated) if manifest.get(key) != regenerated.get(key))
    raise ManifestMismatch(f"the manifest is not what this tree generates: source pins differ for {drift}; "
                           f"sections differ: {sections}")


# ----------------------------------------------------------------------------------------------
# After a granted run: the per-solve record (astra #56701, #56785; aneta #56739)
# ----------------------------------------------------------------------------------------------


def _decimals(path: Path) -> int:
    best = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 2 and "." in fields[1]:
            best = max(best, len(fields[1].split(".")[1]))
    return best


def summarize_evaluation(directory: Path, *, lcf: str = "samplelayers.lcf", grid: str = "sample.grid.steady",
                         steady: str = "sample.steady", config: str = "new_hotspot.config",
                         stdout: str | None = "stdout.txt", chiplet_pattern: str = r"Chiplet_\d+",
                         expected_package: dict | None = None, grid_size: int | None = None,
                         grid_format: str = "all_layers") -> dict:
    """The per-solve record. Reads files only; the grid file is parsed strictly (read_grid).

    grid_format is bound to the evaluator identity (gate_zero.GRID_FORMATS): "all_layers" requires a headered file
    with every layer (HotSpot 7 and the HotSpot 6.0 evaluator build); "upstream6_top_layer" requires upstream
    HotSpot 6.0's headerless layer-0 file. Anything else, a truncated file included, is rejected.
    """
    if grid_format not in ("all_layers", "upstream6_top_layer"):
        raise ValueError(f"unknown grid format {grid_format!r}")
    from sundai_hotspot.gate_zero import tap_selector_c, tap_stdout_selector_c
    directory = Path(directory)
    files = {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
             for path in sorted(directory.iterdir()) if path.is_file()}
    package = read_hotspot_config(directory / config)
    package_record = {name: package.get(name) for name in ("s_spreader", "s_sink", "r_convec", "t_spreader",
                                                           "k_spreader", "t_sink", "k_sink", "ambient",
                                                           "model_secondary", "grid_map_mode")}
    package_ok = None
    if expected_package is not None:
        package_ok = (math.isclose(float(package["s_spreader"]), expected_package["s_spreader_m"], rel_tol=1e-12)
                      and math.isclose(float(package["s_sink"]), expected_package["s_sink_m"], rel_tol=1e-12)
                      and math.isclose(float(package["r_convec"]), expected_package["r_convec_K_per_W"], rel_tol=1e-12))
    ambient = float(package["ambient"])
    layers = read_lcf(directory / lcf, directory)
    power_layers = [layer["layer"] for layer in layers if layer["power"]]
    if len(power_layers) != 1:
        raise ValueError("expected exactly one powered layer")
    active = power_layers[0]
    chip_units = [u for u in read_flp(layers[active]["flp"]) if re.fullmatch(chiplet_pattern, u["name"])]
    if not chip_units:
        raise ValueError("no chiplet blocks matched")
    steady_values = dict(read_steady(directory / steady))
    selector, selector_block = tap_selector_c(directory / steady)
    literal = {"applicable": False, "value_C": None}
    if stdout and (directory / stdout).is_file():
        try:
            literal = {"applicable": True, "value_C": tap_stdout_selector_c(directory / stdout)}
        except ValueError as exc:
            literal = {"applicable": False, "value_C": None,
                       "reason": f"no temperatures on stdout; HotSpot 7 writes none ({type(exc).__name__})"}
    record = {
        "schema": "sentilab-slab049-solve-record-v3",
        "files": files,
        "config_sha256": files[config]["sha256"],
        "output_precision": {"grid_decimals_K": _decimals(directory / grid),
                             "steady_decimals_K": _decimals(directory / steady)},
        "effective_package": package_record,
        "package_matches_fixture": package_ok,
        "historical_tap_stdout_selector": {
            "literal_on_stdout": literal,
            "on_steady_file_C": selector, "block": selector_block,
            "note": "TAP's max(float(stdout.split()[3::2])) - 273.15; HotSpot 6.0 prints the steady dump to stdout",
        },
        "chiplet_block_values_C": {u["name"]: steady_values[f"layer_{active}_{u['name']}"] - KELVIN_OFFSET
                                   for u in chip_units},
    }
    text_layers = len(layers) + 2
    if grid_format == "upstream6_top_layer":
        temperatures = read_grid(directory / grid, grid=grid_size, ambient_k=ambient, headered=False)
        record["grid"] = {"n": math.isqrt(len(temperatures[0])), "layers_in_file": [0], "format": grid_format,
                          "note": "upstream HotSpot 6.0 writes only layer 0; the grid fields need the evaluator build"}
        return record
    temperatures = read_grid(directory / grid, grid=grid_size, layers=text_layers, ambient_k=ambient, headered=True)
    side = math.isqrt(len(temperatures[0]))
    width, height = total_extent(read_flp(layers[0]["flp"]))
    values = temperatures[active]

    def center_value(layer: int, unit: dict) -> tuple[float, list[dict]]:
        mapped = center_cells(block_extent(unit, width, height, side, side))
        return sum(temperatures[layer][c["row"] * side + c["col"]] * c["weight"] for c in mapped), mapped

    chiplets = []
    for unit in chip_units:
        value, mapped = center_value(active, unit)
        chiplets.append({"name": unit["name"], "centre_C": value - KELVIN_OFFSET, "cells": mapped,
                         "distinct_cells": len(mapped)})
    spreader, sink = len(layers), len(layers) + 1
    record.update({
        "grid": {"n": side, "layers_in_file": sorted(temperatures)},
        "active_layer_grid_peak": {"layer": active, "peak_C": max(values) - KELVIN_OFFSET,
                                   "argmax": grid_argmax(values, side)},
        "chiplet_centre_mapping": {"chiplets": chiplets, "max_C": max(c["centre_C"] for c in chiplets),
                                   "rule": "xlate_temp_g2b GRID_CENTER: the mean of 1, 2 or 4 central cells"},
        "spreader_sink_hottest_cell_rises": {
            "spreader": {"layer": spreader, "rise_K": max(temperatures[spreader]) - ambient,
                         "argmax": grid_argmax(temperatures[spreader], side)},
            "sink": {"layer": sink, "rise_K": max(temperatures[sink]) - ambient,
                     "argmax": grid_argmax(temperatures[sink], side)},
            "pattern": run1_pattern(max(temperatures[spreader]) - ambient, max(temperatures[sink]) - ambient),
        },
        "spreader_sink_drop_diagnostic": _same_index_drop(temperatures[spreader], temperatures[sink], side, ambient),
        "same_index_stack_at_active_argmax": same_index_stack(temperatures, layers, side, ambient),
    })
    return record


def _same_index_drop(spreader: list[float], sink: list[float], side: int, ambient: float) -> dict:
    """Same-index spreader and sink observations where their difference is largest. A reported diagnostic."""
    from sundai_hotspot.gate_zero import DROP_EXPECTATION
    index = max(range(len(spreader)), key=lambda i: spreader[i] - sink[i])
    return {"at": {"row": index // side, "col": index % side}, "spreader_K": spreader[index], "sink_K": sink[index],
            "spreader_rise_K": spreader[index] - ambient, "sink_rise_K": sink[index] - ambient,
            "drop_K": spreader[index] - sink[index], "expectation": DROP_EXPECTATION}


def same_index_stack(temperatures: dict[int, list[float]], layers: list[dict], side: int, ambient: float) -> list[dict]:
    """At each active-layer argmax (every tie): the same grid index in every layer from the active one up to the sink,
    with rises above ambient and the layer-to-layer drops. With TAP's six-layer stack these are layers 4 (chip),
    5 (TIM), 6 (spreader) and 7 (sink). A reported diagnostic (astra, native6 review); nothing is asserted on it."""
    powered = [layer["layer"] for layer in layers if layer["power"]]
    if len(powered) != 1:
        raise ValueError("expected exactly one powered layer")
    active = powered[0]
    names = {layer["layer"]: Path(layer["flp"]).stem for layer in layers}
    names.update({len(layers): "spreader", len(layers) + 1: "sink"})
    stacks = []
    for cell in grid_argmax(temperatures[active], side):
        index = cell["row"] * side + cell["col"]
        column = [{"layer": layer, "name": names[layer], "K": temperatures[layer][index],
                   "rise_K": temperatures[layer][index] - ambient} for layer in range(active, len(layers) + 2)]
        stacks.append({"at": cell, "layers": column,
                       "drops": [{"from": upper["name"], "to": lower["name"], "drop_K": upper["K"] - lower["K"]}
                                 for upper, lower in zip(column, column[1:])]})
    return stacks


# ----------------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------------


def _dump(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_or_check(path: Path, data: bytes, check: bool) -> int:
    if check:
        if not path.is_file() or path.read_bytes() != data:
            print(f"MISMATCH: {path}", file=sys.stderr)
            return 1
        print(f"ok: {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("analytic", "slab", "references", "call-list"):
        command = sub.add_parser(name)
        mode = command.add_mutually_exclusive_group(required=True)
        mode.add_argument("--write", type=Path)
        mode.add_argument("--check", type=Path)
    sub.choices["analytic"].add_argument("--no-assembly", action="store_true",
                                         help="skip the C assembly confirmation (it needs gcc and SuperLU)")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("directory", type=Path)
    summarize.add_argument("--fixture-interposer-mm", type=float)
    summarize.add_argument("--slab", action="store_true", help="the directory holds a group (a) slab run")
    args = parser.parse_args(argv)

    if args.command == "summarize":
        expected = tap_package(args.fixture_interposer_mm) if args.fixture_interposer_mm else None
        options = ({"lcf": "slab.lcf", "grid": "slab.grid.steady", "steady": "slab.steady",
                    "config": next(p.name for p in args.directory.glob("slab_h*.config")),
                    "chiplet_pattern": r"die"} if args.slab else {})
        sys.stdout.buffer.write(_dump(summarize_evaluation(args.directory, expected_package=expected, **options)))
        return 0

    target = args.write or args.check
    check = args.check is not None
    if args.command == "analytic":
        report = analytic_report(include_assembly=not args.no_assembly and not check)
        if check:
            committed = json.loads((target / "ANALYTIC.json").read_text(encoding="utf-8"))
            committed.pop("assembly_confirmation", None)
            regenerated = json.loads(_dump(report))
            if committed != regenerated:
                print(f"MISMATCH: {target / 'ANALYTIC.json'}", file=sys.stderr)
                return 1
            print(f"ok: {target / 'ANALYTIC.json'} (frozen equations and residuals)")
            return 0
        return _write_or_check(target / "ANALYTIC.json", _dump(report), check)
    if args.command in ("slab", "references"):
        bundles = ({"slab": slab_files()} if args.command == "slab" else
                   {f"references/{Path(r.inputs).name}": reference_files(r.id) for r in gate_zero.GATE_REFERENCES})
        status = 0
        for folder, files in bundles.items():
            sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
            for name, data in sorted(files.items()):
                status |= _write_or_check(target / folder / name, data, check)
            status |= _write_or_check(target / folder / "SHA256SUMS", sums.encode("ascii"), check)
        return status
    return _write_or_check(target / MANIFEST_NAME, _dump(build_call_list()), check)


if __name__ == "__main__":
    raise SystemExit(main())
