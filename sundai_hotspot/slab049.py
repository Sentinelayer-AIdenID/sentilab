"""SLAB-049 CAL-COUPLING diagnostic tooling. Nothing in this module runs a thermal solve.

    python -m sundai_hotspot.slab049 analytic  [--write DIR | --check DIR]   frozen OLD/NEW links vs h,
                                                                           committed-output residuals,
                                                                           C assembly confirmation (POSIX)
    python -m sundai_hotspot.slab049 slab      [--write DIR | --check DIR]   frozen minimal-slab inputs, group (a)
    python -m sundai_hotspot.slab049 references [--write DIR | --check DIR]  frozen TAP inputs of the published
                                                                           references at 45 mm
    python -m sundai_hotspot.slab049 call-list [--write DIR | --check DIR]   the probe call list for the grant
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
# Published references: frozen TAP inputs at 45 mm, the paper's frame
# ----------------------------------------------------------------------------------------------

HOTSPOT6 = "hotspot6"
PAPER = "Ma et al., TAP-2.5D, DATE 2021 (HotSpot 6.0, 45 mm interposer, grid 64, 45 C ambient)"
ASCEND_PLACED_DIMS = [[31.4, 14.5], [10.5, 16.0], [11.87, 7.75], [11.87, 7.75], [11.87, 7.75], [11.87, 7.75]]
REFERENCE_LAYOUTS = {
    "ascend910-original": {
        "fixture": "ascend910", "paper_figure": "Fig. 6(a) original layout", "paper_peak_c": 75.48,
        "centers_mm": [[17.15, 22.60], [38.35, 22.60], [7.34, 11.12], [21.31, 11.12], [7.34, 33.87], [21.31, 33.87]],
        "placed_dims_mm": ASCEND_PLACED_DIMS,
        "orientation_note": ("Virtuvian and the HBMs sit rotated 90 degrees from the catalog. TAP's microbump halo "
                             "depends on the perimeter only (passive_interposer.py compute_ubump_overhead), so it "
                             "is unchanged."),
    },
    "micro150-original": {
        "fixture": "micro150", "paper_figure": "Fig. 5(a) original placement (Kannan et al., MICRO 2015)",
        "paper_peak_c": 115.94,
        "centers_mm": [[17.92, 17.55], [17.92, 27.45], [27.07, 27.45], [27.07, 17.55],
                       [8.57, 17.55], [8.57, 27.45], [36.42, 27.45], [36.42, 17.55]],
        "placed_dims_mm": None,
        "orientation_note": ("Catalog orientation. CPUs 0-3 go around the 2x2 cluster so the 0-1-2-3 ring is "
                             "adjacent; DRAM 4+i sits beside CPU i. Equal dies carry equal power, so the index "
                             "assignment changes the wire proxy only."),
    },
    "ascend910-tap": {
        "fixture": "ascend910", "paper_figure": "Fig. 6(c) TAP-2.5D solution", "paper_peak_c": 75.47,
        "centers_mm": [[17.0, 25.0], [39.0, 25.0], [11.0, 13.0], [24.0, 13.0], [10.0, 37.0], [23.0, 37.0]],
        "placed_dims_mm": ASCEND_PLACED_DIMS,
        "orientation_note": "orientations assumed as in the original layout; the paper's panels share its structure",
    },
    "micro150-tap": {
        "fixture": "micro150", "paper_figure": "Fig. 5 TAP-2.5D solution (non-pipelined links)", "paper_peak_c": 94.89,
        "centers_mm": None, "placed_dims_mm": None,
        "orientation_note": "pending: the DRAM positions are not decoded; SLAB-048 supplies them",
    },
}
REFERENCE_SOURCE = ("forge-research/repo-forensics.md section 6, decoded from the paper's vector figures; "
                    "SLAB-048 reference data supersedes it before any run (regenerate the manifest, never swap after)")
# (layout, variant): raw is the decoded reconstruction; snapped is its legal 1 mm snap. They are separate identities.
REFERENCE_SETS = (("ascend910-original", "raw"), ("ascend910-original", "snapped"), ("micro150-original", "raw"),
                  ("micro150-original", "snapped"), ("ascend910-tap", "raw"))
REFERENCE_INPUTS = ("new_hotspot.config", "samplelayers.lcf", "sample.ptrace", "sampleL0_Substrate.flp",
                    "sampleL1_C4Layer.flp", "sampleL2_Interposer.flp", "sampleL3_UbumpLayer.flp",
                    "sampleL4_ChipLayer.flp", "sampleL5_TIM.flp")
_GENERATOR = r"""
import json, sys
from passive_interposer import PassiveInterposer
spec, out = json.loads(sys.argv[1]), sys.argv[2]
system = PassiveInterposer()
system.set_chiplet_count(len(spec["widths"]))
system.initialize()
system.set_interposer_size(spec["interposer_mm"])
system.set_chiplet_size(spec["widths"], spec["heights"])
system.set_chiplet_power(spec["powers"])
system.set_connection_matrix(spec["connections"])
system.set_granularity(spec["granularity"])
system.set_link_type(spec["link_type"])
system.compute_ubump_overhead()
system.set_path(out + "/")
system.x, system.y = spec["x"], spec["y"]
system.gen_flp("sample")
system.gen_ptrace("sample")
"""
MARGIN_MM = 0.5  # the oracle's interposer margin, microbump halo included


def _fixture_problem(fixture: str):
    from sundai_hotspot.tap_oracle import TAP_CONFIGS, _load_problem
    with tempfile.TemporaryDirectory(prefix="slab049-problem-") as directory:
        placeholder = Path(directory) / "hotspot-placeholder"
        placeholder.write_bytes(b"problem parameters only; never executed")
        return _load_problem(config_path=TAP_CONFIGS[fixture], hotspot_binary=placeholder)


def layout_problems(dims: list[list[float]], centers: list[list[float]], halos: list[float], size: float) -> list[str]:
    """The oracle's legality rules for any orientation: margin with halo, no halo overlap (touching allowed)."""
    rects = [(x - w / 2 - h, y - d / 2 - h, x + w / 2 + h, y + d / 2 + h)
             for (w, d), (x, y), h in zip(dims, centers, halos)]
    problems = [f"die {i} breaks the {MARGIN_MM} mm margin" for i, r in enumerate(rects)
                if r[0] < MARGIN_MM - 1e-9 or r[1] < MARGIN_MM - 1e-9 or r[2] > size - MARGIN_MM + 1e-9
                or r[3] > size - MARGIN_MM + 1e-9]
    for i, a in enumerate(rects):
        for j, b in enumerate(rects[:i]):
            if not (a[2] <= b[0] + 1e-9 or b[2] <= a[0] + 1e-9 or a[3] <= b[1] + 1e-9 or b[3] <= a[1] + 1e-9):
                problems.append(f"dies {j} and {i} overlap with their halos")
    return problems


_SNAP_OFFSETS = sorted(((dx, dy) for dx in range(-3, 4) for dy in range(-3, 4)),
                       key=lambda d: (abs(d[0]) + abs(d[1]), abs(d[1]), d[0] < 0, d[1] < 0))


def snap_legal(dims: list[list[float]], centers: list[list[float]], halos: list[float], size: float) -> list[list[float]]:
    """Deterministic legal 1 mm snap: round each centre half up; in index order, take the first offset (nearest
    first, x moves before y, positive before negative) that keeps the margin and clears every die placed so far."""
    placed: list[list[float]] = []
    for index, (x, y) in enumerate(centers):
        base = (math.floor(x + 0.5), math.floor(y + 0.5))
        for dx, dy in _SNAP_OFFSETS:
            candidate = [float(base[0] + dx), float(base[1] + dy)]
            if not layout_problems(dims[:index + 1], placed + [candidate], halos[:index + 1], size):
                placed.append(candidate)
                break
        else:
            raise ValueError(f"die {index} has no legal 1 mm position within 3 mm of its decoded centre")
    return placed


def reference_spec(layout_id: str, variant: str, interposer_mm: int = 45) -> dict:
    layout = REFERENCE_LAYOUTS[layout_id]
    if layout["centers_mm"] is None:
        raise ValueError(f"{layout_id} is pending: {layout['orientation_note']}")
    problem = _fixture_problem(layout["fixture"])
    catalog = [list(d) for d in zip(problem.widths_mm, problem.heights_mm)]
    dims = layout["placed_dims_mm"] or catalog
    if sorted(map(sorted, dims)) != sorted(map(sorted, catalog)):
        raise ValueError(f"{layout_id}: placed dies are not the fixture's catalog dies")
    halos = list(problem.bump_halos_mm)
    centers = [list(c) for c in layout["centers_mm"]]
    if variant == "snapped":
        centers = snap_legal(dims, centers, halos, interposer_mm)
    elif variant != "raw":
        raise ValueError(f"unknown variant {variant!r}")
    return {"interposer_mm": float(interposer_mm), "widths": [d[0] for d in dims], "heights": [d[1] for d in dims],
            "powers": list(problem.powers_w), "connections": [list(row) for row in problem.connections],
            "granularity": problem.granularity_mm, "link_type": problem.link_type, "halos": halos,
            "x": [c[0] for c in centers], "y": [c[1] for c in centers],
            "legality_problems": layout_problems(dims, centers, halos, interposer_mm)}


def generate_reference(spec: dict, directory: Path) -> dict[str, bytes]:
    """Run TAP's own generator for `spec` in `directory`; return the HotSpot inputs with a local, LF-only LCF."""
    from sundai_hotspot.tap_oracle import TAP_ROOT
    process = subprocess.run([sys.executable, "-c", _GENERATOR, json.dumps(spec), str(directory)], cwd=TAP_ROOT,
                             capture_output=True, text=True, check=False, timeout=120)
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


def reference_files(layout_id: str, variant: str) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="slab049-reference-") as directory:
        return generate_reference(reference_spec(layout_id, variant), Path(directory))


def reference_dir(layout_id: str, variant: str) -> str:
    return f"docs/sentilab/diagnostics/SLAB-049/references/{layout_id}-{variant}-45mm"


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
# The manifest: one frozen list of at most 12 calls (astra #56794)
# ----------------------------------------------------------------------------------------------

MANIFEST_ENGINES = (("HS6", HOTSPOT6), ("HS7", "hotspot7_default"))
MANIFEST_REFERENCES = ("ascend910-original", "micro150-original")
PRIMARY_VARIANT = "snapped"
PRIMARY_VARIANT_REASON = (
    "The legal snapped variant passes the same constraint checker that every search candidate must pass (margin, "
    "halos, 1 mm grid), so a later MATCH compares like with like. The raw reconstruction carries the figure's "
    "digitizing noise and off-grid positions that search can never reach. Snapping moves no die more than its "
    "rounding plus the first clear 1 mm offset; on Ascend 910 the paper's three layouts differ by only 0.35 K. "
    "Risk, declared now: if a snapped reference misses by more than 1.0 K, the raw run in the next allocation "
    "separates snapping from physics before the evaluator is called wrong.")
TIMING = {  # micro150/TIMING.json, Azure x86_64 (16 CPU); HotSpot 6.0 SuperLU is unmeasured and assumed alike
    "grid64_expected_wall_s": 4.76,
    "grid32_expected_wall_s": 0.49,
    "per_call_overhead_cpu_s": 1.5,  # TAP generation, hashing, process start and reap, archive, summary
    "grid64_cpu_cap_s": 60.0,        # each call is killed at its cap; a failed attempt costs at most that
    "grid32_cpu_cap_s": 15.0,
}
MANIFEST_SOURCES = (
    "scripts/build_hotspot6.sh", "sundai_hotspot/Makefile", "sundai_hotspot/temperature_grid.c",
    "sundai_hotspot/tap_oracle.py", "sundai_hotspot/tap_oracle_worker.py", "sundai_hotspot/gate_zero.py",
    "sundai_hotspot/evaluators.py", "sundai_hotspot/reference_validation.py", "sundai_hotspot/slab049.py",
    "sundai_hotspot6/UPSTREAM_COMMIT", "sundai_hotspot6/UPSTREAM_BLOBS.txt", "sundai_hotspot6/temperature_grid.c",
    "sundai_hotspot6/Makefile", "sundai_tap/passive_interposer.py", "sundai_tap/system.py",
    "sundai_tap/util/hotspot.config", "sundai_tap/util/fill_space.py", "sundai_tap/configs/sys_ascend910.cfg",
    "sundai_tap/configs/sys_micro150.cfg",
)


def _sums_digest(directory: str) -> str:
    return hashlib.sha256((REPO_ROOT / directory / "SHA256SUMS").read_bytes()).hexdigest()


def _manifest_call(call_id: str, label: str, kind: str, layout_id: str, grid: int, purpose: str,
                   replay_of: str | None = None) -> dict:
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS
    directory = reference_dir(layout_id, PRIMARY_VARIANT)
    cap = TIMING[f"grid{grid}_cpu_cap_s"]
    return {
        "id": call_id, "engine": label, "kind": kind, "binary": EVALUATOR_KINDS[kind]["binary"],
        "reference": f"{layout_id}-{PRIMARY_VARIANT}", "paper_peak_c": REFERENCE_LAYOUTS[layout_id]["paper_peak_c"],
        "grid": grid, "gating": grid == 64 and kind == HOTSPOT6 and replay_of is None, "purpose": purpose,
        "replay_of": replay_of,
        "inputs": {"dir": directory, "sha256sums_sha256": _sums_digest(directory)},
        "command": (f"python -m sundai_hotspot.reference_validation validate-reference --call {call_id} "
                    "--out <fresh empty dir> --ledger <the grant's ledger dir>"),
        "argv": tap_argv(f"<repo>/{EVALUATOR_KINDS[kind]['binary']}", grid),
        "accounting": {"expected_wall_s": TIMING[f"grid{grid}_expected_wall_s"],
                       "expected_cpu_s": round(TIMING[f"grid{grid}_expected_wall_s"] + TIMING["per_call_overhead_cpu_s"], 2),
                       "cpu_cap_s": cap, "solver_timeout_s": cap,
                       "worst_case_cpu_s": cap + TIMING["per_call_overhead_cpu_s"]},
    }


def build_call_list() -> dict:
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS, PINNED_REFERENCES_SHA256, TOLERANCE_K, TOLERANCE_LABEL
    calls = []
    for label, kind in MANIFEST_ENGINES:
        for layout_id in MANIFEST_REFERENCES:
            for grid in (64, 32):
                purpose = ("gate zero: the block-centre metric within 1.0 K of the paper" if kind == HOTSPOT6 and grid == 64
                           else "numerical evidence, not gating: " + ("current engine at the paper's grid" if grid == 64
                                                                     else "grid 32 against grid 64"))
                calls.append(_manifest_call(f"p-{label.lower()}-{layout_id}-g{grid}", label, kind, layout_id, grid,
                                            purpose))
    for label, kind in MANIFEST_ENGINES:
        for layout_id in MANIFEST_REFERENCES:
            primary = f"p-{label.lower()}-{layout_id}-g64"
            calls.append(_manifest_call(f"r-{label.lower()}-{layout_id}-g64", label, kind, layout_id, 64,
                                        "independent fresh-process replay: outputs must be byte-identical",
                                        replay_of=primary))
    expected = sum(c["accounting"]["expected_cpu_s"] for c in calls)
    worst = sum(c["accounting"]["worst_case_cpu_s"] for c in calls)
    return {
        "schema": "sentilab-slab049-manifest-v3",
        "ticket": TICKET,
        "ticket_uuid": TICKET_UUID,
        "status": ("PROPOSED. Frozen manifest of 12 calls for warden's grant against the merged build. Nothing has "
                   "been executed; no solve has been run for SLAB-049."),
        "generated_by": "python -m sundai_hotspot.slab049 call-list --write docs/sentilab/diagnostics/SLAB-049",
        "paper": PAPER,
        "grant_window": {"not_before": "warden's grant against the merged build",
                         "not_after_utc": "2026-11-01T12:00:00Z",
                         "per_call_receipts_record": "effective start and stop (UTC), wall and child CPU seconds"},
        "source": {"pin": "SHA-256 of every file that builds, stages or judges the calls; the merged build must match",
                   "files_sha256": {path: hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
                                    for path in MANIFEST_SOURCES}},
        "builds": {
            kind: {"command": EVALUATOR_KINDS[kind]["build"], "binary": EVALUATOR_KINDS[kind]["binary"],
                   "upstream": EVALUATOR_KINDS[kind]["upstream"],
                   "binary_sha256": "recorded at build on the grant host; every receipt binds it",
                   "identity_markers": {"required": [m.decode("ascii") for m in EVALUATOR_KINDS[kind]["required_markers"]],
                                        "forbidden": [m.decode("ascii") for m in EVALUATOR_KINDS[kind]["forbidden_markers"]]}}
            for _, kind in MANIFEST_ENGINES},
        "references": {f"{layout}-{variant}": {"dir": reference_dir(layout, variant),
                                               "sha256sums_sha256": _sums_digest(reference_dir(layout, variant)),
                                               "paper_peak_c": REFERENCE_LAYOUTS[layout]["paper_peak_c"],
                                               "in_this_manifest": layout in MANIFEST_REFERENCES and variant == PRIMARY_VARIANT}
                       for layout, variant in REFERENCE_SETS},
        "reference_layouts": REFERENCE_LAYOUTS,
        "reference_source": REFERENCE_SOURCE,
        "primary_variant": PRIMARY_VARIANT,
        "primary_variant_reason": PRIMARY_VARIANT_REASON,
        "gate_zero": {"module": "sundai_hotspot/gate_zero.py", "tolerance_k": TOLERANCE_K,
                      "tolerance_label": TOLERANCE_LABEL, "pinned_references_sha256": PINNED_REFERENCES_SHA256,
                      "pinned_values_c": {"ascend910-original": 75.48, "micro150-original": 115.94,
                                          "ascend910-tap (verification, next allocation)": 75.47,
                                          "micro150-tap (verification, next allocation)": 94.89}},
        "calls": calls,
        "accounting": {
            "calls": len(calls), "max_runs": len(calls), "retries": 0,
            "timing_basis": TIMING,
            "expected_cpu_s": round(expected, 2),
            "worst_case_cpu_s": round(worst, 2),
            "cpu_cap_minutes": math.ceil(worst / 60),
            "cpu_cap_rule": "every call killed at its cap plus its overhead: the sum is the worst case",
            "failed_attempt_reserve": "inside each call's cap; a failed attempt is not retried under this grant",
            "concurrency": 1, "gpu": False,
            "host": "x86_64 Azure host behind the mesh and TIMING evidence; an aarch64 build needs its own receipts",
            "host_architecture": "x86_64",
            "enforced_at_entry": ("validate-reference runs only a listed call id with its listed engine, reference and "
                                  "grid; refuses after the window, on another architecture, or a second time (the "
                                  "ledger reserves each call once); sets RLIMIT_CPU to the call's CPU cap and a wall "
                                  "timeout of twice the cap; writes the reservation and identity before launch and "
                                  "settles the receipt on every exit path"),
        },
        "next_allocation": [
            "raw reconstructions of both originals on HS6 at grid 64 (a separate reference identity)",
            "verification cases, not a statistical holdout: ascend910-tap 75.47 C and micro150-tap 94.89 C "
            "(layout pending SLAB-048)",
            "HotSpot 6.0 built SUPERLU=0 exactly as TAP-2.5D's util/hotspot (kind hotspot6_tap_faithful) on both "
            "originals: the solver cross-check",
            "the aarch64 (GB10) build's own gate-zero receipts",
            "a 50 mm frame comparison and NEW-evaluator mesh margins",
        ],
        "separate_allocations": [
            {**KNOWN_ANSWER_SLAB, "calls": 2, "engines": ["hotspot6", "hotspot7_default"],
             "in_this_manifest": False, "gate_zero_calls": False,
             "expected_rise_K": {kind: known_answer_expected(kind)["expected_rise_K"]
                                 for kind in ("hotspot6", "hotspot7_default")},
             "equations": "slab049.known_answer_expected docstring: geometry, power, area, node and boundary "
                          "equations, the series-resistance derivation, and when the slab result applies"},
            {"id": "24-layout re-score study", "in_this_manifest": False,
             "note": "a later separate allocation; not folded into this manifest"},
        ],
        "post_run_diagnostics": ("From the 12 calls, with no extra call (reference_validation report): HotSpot 6.0's "
                                 "grid 32 -> 64 change per fixture (aneta's network model predicts 0.01 K Ascend, "
                                 "0.18 K CPU-DRAM; the old HotSpot 7 micro150 mesh error was 0.79 K), CPU-s per call "
                                 "on the HotSpot 6.0 build, replay byte-identity, and the same-index spreader-sink "
                                 "drop (reported, not asserted). Nothing is frozen on them or on the old mesh error."),
        "not_requested": ("The v1 and v2 plans (32 calls, 37 executions; later 23) and every material-only HotSpot 7 "
                          "call. The material-only flag stays as labelled, bounded diagnostic evidence; it is not the "
                          "MATCH evaluator and inherits no grant."),
    }


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
    })
    return record


def _same_index_drop(spreader: list[float], sink: list[float], side: int, ambient: float) -> dict:
    """Same-index spreader and sink observations where their difference is largest. A reported diagnostic."""
    from sundai_hotspot.gate_zero import DROP_EXPECTATION
    index = max(range(len(spreader)), key=lambda i: spreader[i] - sink[i])
    return {"at": {"row": index // side, "col": index % side}, "spreader_K": spreader[index], "sink_K": sink[index],
            "spreader_rise_K": spreader[index] - ambient, "sink_rise_K": sink[index] - ambient,
            "drop_K": spreader[index] - sink[index], "expectation": DROP_EXPECTATION}


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
                   {f"references/{layout}-{variant}-45mm": reference_files(layout, variant)
                    for layout, variant in REFERENCE_SETS})
        status = 0
        for folder, files in bundles.items():
            sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
            for name, data in sorted(files.items()):
                status |= _write_or_check(target / folder / name, data, check)
            status |= _write_or_check(target / folder / "SHA256SUMS", sums.encode("ascii"), check)
        return status
    return _write_or_check(target / "CALL-LIST.json", _dump(build_call_list()), check)


if __name__ == "__main__":
    raise SystemExit(main())
