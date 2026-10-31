"""SLAB-049 CAL-COUPLING diagnostic tooling. Nothing in this module runs a thermal solve.

    python -m sundai_hotspot.slab049 analytic  [--write DIR | --check DIR]   frozen OLD/NEW links vs h,
                                                                           committed-output residuals,
                                                                           C assembly confirmation (POSIX)
    python -m sundai_hotspot.slab049 slab      [--write DIR | --check DIR]   frozen minimal-slab inputs, group (a)
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
    COUPLINGS, NEW, OLD, VARIANT_MACRO, VARIANT_MAKE_TARGET, VARIANT_TAG, PackageStack, area_resistances,
    cell_resistances,
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


def read_grid(path: Path) -> dict[int, list[float]]:
    layers: dict[int, list[float]] = {}
    current = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.fullmatch(r"Layer\s+(\d+):", stripped)
        if match:
            current = int(match.group(1))
            layers[current] = []
            continue
        index, value = stripped.split()
        if int(index) != len(layers[current]):
            raise ValueError("non-sequential grid index")
        layers[current].append(float(value))
    return layers


def read_steady(path: Path) -> list[tuple[str, float]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 2:
            rows.append((fields[0], float(fields[1])))
    return rows


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
            measured = run["vertical"][(run["spreader"], run["sink"])]
            rows.append({
                "h_multiplier": multiplier, "coupling": coupling, "grid": 16,
                "assembled_spreader_sink_K_per_W": measured,
                "frozen_equation_spreader_sink_K_per_W": frozen.spreader_sink,
                "bit_identical": measured == frozen.spreader_sink,
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


def slab_prediction(coupling: str, multiplier: float) -> dict:
    """Closed-form 1-D column, node temperatures above ambient (K) at the die centre.

    find_res pairs: die(0)-TIM(1) = r_die + r_tim/2 (layer 0 keeps its full rz), TIM-spreader = r_tim/2 + r_sp/2,
    spreader-sink per coupling, sink-ambient = r_hs,mat + r_conv. All heat leaves through the sink.
    """
    config = read_hotspot_config(TAP_HOTSPOT_CONFIG)
    stack = PackageStack(float(config["k_spreader"]), float(config["t_spreader"]), float(config["k_sink"]),
                         float(config["t_sink"]), slab_r_convec(multiplier), SLAB["s_sink_m"])
    links = area_resistances(stack, coupling)
    r_die = SLAB["die"]["resistivity"] * SLAB["die"]["thickness"]
    r_tim = SLAB["tim"]["resistivity"] * SLAB["tim"]["thickness"]
    r_sp = stack.t_spreader / stack.k_spreader
    flux = SLAB["power_W"] / (SLAB["die_edge_m"] ** 2)
    sink = flux * links["sink_ambient"]
    spreader = sink + flux * links["spreader_sink"]
    tim = spreader + flux * (r_tim / 2 + r_sp / 2)
    die = tim + flux * (r_die + r_tim / 2)
    return {"flux_W_per_m2": flux, "h_W_per_m2K": stack.heat_transfer_coefficient,
            "rise_K": {"die_layer0": die, "tim_layer1": tim, "spreader_layer2": spreader, "sink_layer3": sink},
            "interior_drop_die_minus_sink_K": die - sink}


# ----------------------------------------------------------------------------------------------
# Groups (b) and (c): TAP layouts
# ----------------------------------------------------------------------------------------------

PAPER = "Ma et al., TAP-2.5D, DATE 2021 (HotSpot 6.0, 45 mm interposer, grid 64, 45 C ambient)"
ORIGINAL_LAYOUTS = {
    "ascend910-original": {
        "fixture_family": "ascend910",
        "paper_figure": "Fig. 6(a) original layout",
        "paper_peak_c": 75.48,
        "decoded_centers_mm_45mm_frame": [[17.15, 22.60], [38.35, 22.60], [7.34, 11.12], [21.31, 11.12],
                                          [7.34, 33.87], [21.31, 33.87]],
        "decoded_orientation": ("Virtuvian 31.4 x 14.5 (horizontal), Nimbus 10.5 x 16, HBM 11.87 x 7.75 (rotated); "
                                "the catalog fixes Virtuvian 14.5 x 31.4 and HBM 7.75 x 11.87"),
        "source": "forge-research/repo-forensics.md section 6 (decoded from the paper's vector figure)",
    },
    "micro150-original": {
        "fixture_family": "micro150",
        "paper_figure": "Fig. 5(a) original placement (Kannan et al., MICRO 2015)",
        "paper_peak_c": 115.94,
        "decoded_centers_mm_45mm_frame": [[17.92, 17.55], [17.92, 27.45], [27.07, 27.45], [27.07, 17.55],
                                          [8.57, 17.55], [8.57, 27.45], [36.42, 27.45], [36.42, 17.55]],
        "decoded_orientation": "CPU 8.25 x 9 and DRAM 8.75 x 8.75, catalog orientation",
        "index_assignment": ("CPUs 0-3 around the 2x2 cluster so the 0-1-2-3 ring is adjacent, DRAM 4+i beside "
                             "CPU i. Equal dies have equal power, so the assignment changes the wire proxy only."),
        "source": "forge-research/repo-forensics.md section 6 (decoded from the paper's vector figure)",
    },
}


def provisional_50mm_centers(centers_45: list[list[float]]) -> list[list[float]]:
    """Shift the 45 mm frame by +2.5 mm into the 50 mm frame, then round to the oracle's 1 mm centre grid."""
    return [[float(math.floor(x + 2.5 + 0.5)), float(math.floor(y + 2.5 + 0.5))] for x, y in centers_45]


def _legal(fixture: str, centers: list[list[float]]) -> tuple[bool, str]:
    from sundai_hotspot.tap_oracle import HotSpotOracle, TapLegalityError
    with tempfile.TemporaryDirectory(prefix="slab049-legality-") as directory:
        placeholder = Path(directory) / "hotspot-placeholder"
        placeholder.write_bytes(b"legality check only; never executed")
        oracle = HotSpotOracle(64, 64, fixture=fixture, hotspot_binary=placeholder)
        try:
            oracle.centers_for(oracle.design_from_centers([tuple(c) for c in centers]))
        except TapLegalityError as exc:
            return False, str(exc)
    return True, "passes the oracle's catalog, margin, halo-overlap and 1 mm grid checks"


def mesh_subset(fixture: str) -> tuple[list[dict], dict]:
    """The layout that set the fixture's mesh error, plus clustered-01, spread-01 and random-01."""
    result = json.loads((REPO_ROOT / "docs/sentilab/evidence/mesh" / fixture / "RESULT.json").read_text())
    rows = sorted(result["layouts"], key=lambda r: (-abs(r["J_c"]["32"] - r["J_c"]["64"]), r["id"]))
    chosen = [rows[0]]
    for wanted in ("clustered-01", "spread-01", "random-01"):
        row = next(r for r in result["layouts"] if r["id"] == wanted)
        if row not in chosen:
            chosen.append(row)
    for row in rows:
        if len(chosen) >= 4:
            break
        if row not in chosen:
            chosen.append(row)
    epsilon = max(abs(r["J_c"]["32"] - r["J_c"]["64"]) for r in result["layouts"])
    return chosen, {"epsilon_c": epsilon, "argmax_layout": rows[0]["id"]}


# ----------------------------------------------------------------------------------------------
# The call list
# ----------------------------------------------------------------------------------------------

EVALUATORS = {
    "OLD": {
        "coupling": OLD,
        "build": "make -C sundai_hotspot -j4 SUPERLU=1",
        "binary": "sundai_hotspot/hotspot",
        "oracle": ("sundai_hotspot.tap_oracle.HotSpotOracle(64, 64, fixture=..., max_workers=1, "
                   "retained_output_root=<fresh dir>)"),
        "identity_checks": ["binary must NOT contain the SLAB-049 tag", "problem_hash is the unchanged default"],
    },
    "NEW": {
        "coupling": NEW,
        "build": f"make -C sundai_hotspot SUPERLU=1 {VARIANT_MAKE_TARGET}",
        "binary": f"sundai_hotspot/{VARIANT_MAKE_TARGET}",
        "oracle": ("sundai_hotspot.coupling_variant.MaterialOnlyCouplingOracle(64, 64, fixture=..., max_workers=1, "
                   "retained_output_root=<fresh dir>)"),
        "identity_checks": [f"binary must contain {VARIANT_TAG.decode()}",
                            "solver_version and problem_hash name coupling=material_only"],
    },
}

# Measured costs (see CALL-LIST.md for sources). CPU seconds per call, including worker start and reap.
COST = {
    "grid64_typical_cpu_s": 4.90,     # micro150 mesh: 129.79 CPU-s / 72 calls, grid-64 share of wall time
    "grid64_conservative_cpu_s": 7.84,  # slowest grid-64 evaluation in the micro150 mesh journal
    "grid32_typical_cpu_s": 0.5435,   # SLAB-039: 1,440.29 CPU-s / 2,650 grid-32 calls
    "grid32_conservative_cpu_s": 0.60,
    "per_call_archive_cpu_s": 0.5,    # hashing and summarizing the retained files
    "retry_reserve_calls": 4,
    "timeout_reserve_calls": 1,
    "timeout_cpu_s": 55.0,            # 45 s solver timeout + 10 s worker margin
}


def _fixture(family: str, interposer: int) -> dict:
    package = tap_package(interposer)
    available = interposer == 50
    return {
        "family": family,
        "interposer_mm": interposer,
        "spreader_mm": round(package["s_spreader_m"] * 1000, 9),
        "sink_mm": round(package["s_sink_m"] * 1000, 9),
        "r_convec_K_per_W": package["r_convec_K_per_W"],
        "available_on_main": available,
        "oracle_fixture_id": family if available else None,
        "blocked_on": None if available else "SLAB-048: a 45 mm fixture in tap_oracle.TAP_CONFIGS",
    }


def build_call_list() -> dict:
    fixtures = {f"{family}@{size}mm": _fixture(family, size)
                for family in ("ascend910", "micro150") for size in (45, 50)}
    calls = []

    for multiplier in H_MULTIPLIERS:
        for evaluator in ("OLD", "NEW"):
            coupling = EVALUATORS[evaluator]["coupling"]
            calls.append({
                "id": f"a-slab-{_slab_label(multiplier)}-{evaluator.lower()}",
                "group": "a", "evaluator": evaluator, "grid": SLAB["grid"], "status": "ready",
                "h_multiplier": multiplier, "r_convec_K_per_W": slab_r_convec(multiplier),
                "invocation": {
                    "cwd": "<fresh empty directory>",
                    "copy_in": ["slab_die.flp", "slab_tim.flp", "slab.lcf", "slab.ptrace",
                                f"slab_{_slab_label(multiplier)}.config"],
                    "verify": "every copied file matches slab/SHA256SUMS before the solver starts",
                    "argv": slab_argv(f"<repo>/{EVALUATORS[evaluator]['binary']}", multiplier),
                },
                "prediction": slab_prediction(coupling, multiplier),
            })

    for layout_id, layout in ORIGINAL_LAYOUTS.items():
        for size in (45, 50):
            fixture_key = f"{layout['fixture_family']}@{size}mm"
            fixture = fixtures[fixture_key]
            centers = None
            blocked = []
            if not fixture["available_on_main"]:
                blocked.append(fixture["blocked_on"])
            if layout_id == "ascend910-original":
                blocked.append("SLAB-048: per-die orientation (Virtuvian, HBM and Nimbus orientations are not in the "
                               "catalog) and off-grid reference centres")
            elif size == 45:
                blocked.append("SLAB-048: reference centres for the 45 mm frame (nearest-mm rounding overlaps the "
                               "CPU halos in y)")
            else:
                centers = provisional_50mm_centers(layout["decoded_centers_mm_45mm_frame"])
                legal, reason = _legal(layout["fixture_family"], centers)
                if not legal:
                    blocked.append(f"provisional 50 mm centres are illegal: {reason}")
            for evaluator in ("OLD", "NEW"):
                calls.append({
                    "id": f"b-{layout_id}-{size}mm-{evaluator.lower()}",
                    "group": "b", "evaluator": evaluator, "grid": 64, "fixture": fixture_key,
                    "layout": layout_id,
                    "centers_mm": centers,
                    "centers_note": ("PROVISIONAL: decoded 45 mm centres +2.5 mm, rounded to 1 mm; SLAB-048 reference "
                                     "data supersedes this before any run (regenerate the list, never swap after)"
                                     if centers else None),
                    "status": "blocked" if blocked else "ready",
                    "blocked_on": blocked or None,
                    "paper_peak_c": layout["paper_peak_c"],
                })

    mesh = {}
    for fixture in ("ascend910", "micro150"):
        subset, summary = mesh_subset(fixture)
        mesh[fixture] = {**summary, "layouts": [row["id"] for row in subset]}
        for row in subset:
            for grid in (32, 64):
                calls.append({
                    "id": f"c-mesh-{fixture}-{row['id']}-g{grid}-new",
                    "group": "c", "evaluator": "NEW", "grid": grid, "fixture": f"{fixture}@50mm",
                    "layout": f"mesh/{fixture}/{row['id']}", "centers_mm": row["centers_mm"], "status": "ready",
                    "old_reference_j_c": row["J_c"][str(grid)],
                })
        argmax = subset[0]
        calls.append({
            "id": f"c-mesh-{fixture}-{argmax['id']}-g64-old-reproduction",
            "group": "c", "evaluator": "OLD", "grid": 64, "fixture": f"{fixture}@50mm",
            "layout": f"mesh/{fixture}/{argmax['id']}", "centers_mm": argmax["centers_mm"], "status": "ready",
            "old_reference_j_c": argmax["J_c"]["64"],
            "purpose": "ties this host's OLD binary to the committed mesh J64 before NEW is compared with it",
        })

    def cost(call: dict, key: str) -> float:
        return COST[f"grid{call['grid']}_{key}_cpu_s"]

    ready = [c for c in calls if c["status"] == "ready"]
    blocked = [c for c in calls if c["status"] == "blocked"]

    def tier(selection: list[dict]) -> dict:
        typical = sum(cost(c, "typical") for c in selection)
        conservative = sum(cost(c, "conservative") for c in selection)
        return {"calls": len(selection),
                "grid64_calls": sum(c["grid"] == 64 for c in selection),
                "grid32_calls": sum(c["grid"] == 32 for c in selection),
                "typical_cpu_s": round(typical, 2), "conservative_cpu_s": round(conservative, 2)}

    reserve = (COST["retry_reserve_calls"] * COST["grid64_conservative_cpu_s"]
               + COST["timeout_reserve_calls"] * COST["timeout_cpu_s"]
               + len(calls) * COST["per_call_archive_cpu_s"])
    all_tiers = tier(calls)
    total = all_tiers["conservative_cpu_s"] + reserve
    return {
        "schema": "sentilab-slab049-call-list-v1",
        "ticket": TICKET,
        "ticket_uuid": TICKET_UUID,
        "status": "PROPOSED. Not executed. Every call needs warden's grant; no solve has been run for SLAB-049.",
        "pristine_source_commit": BASE_COMMIT,
        "generated_by": "python -m sundai_hotspot.slab049 call-list --write docs/sentilab/diagnostics/SLAB-049",
        "paper": PAPER,
        "evaluators": EVALUATORS,
        "fixtures": fixtures,
        "original_layouts": ORIGINAL_LAYOUTS,
        "slab": {**SLAB, "inputs": "docs/sentilab/diagnostics/SLAB-049/slab/ (SHA256SUMS)",
                 "r_convec_K_per_W_by_h": {f"{m:g}": slab_r_convec(m) for m in H_MULTIPLIERS}},
        "mesh_subset": mesh,
        "per_call_record": [
            "python -m sundai_hotspot.slab049 summarize <retained evaluation dir> (reads files only):",
            "SHA-256 and size of every generated input and output file, including the actual config",
            "output precision: HotSpot prints grid and block temperatures as %.2f K",
            "package parameters read back from the actual config (spreader, sink, r_convec) and checked "
            "against the fixture row",
            "layer-4 grid peak and its argmax cell(s)",
            "each real chiplet's GRID_CENTER value with the cell indices and weights (1, 2 or 4 cells)",
            "the max over those chiplet centre values",
            "TAP's positional stdout selector: on this binary's stdout (HotSpot 7 prints no temperatures, so it "
            "is recorded as not applicable) and emulated on HotSpot 6's stdout layout (every block of every "
            "layer centre-mapped, plus the package nodes)",
        ],
        "per_call_rules": [
            "each call runs in a fresh, empty directory; the TAP generator skips an existing new_hotspot.config, "
            "so a reused directory could run a stale config",
            "max_workers=1: one solver process at a time",
            "no parameter is changed between OLD and NEW: same inputs, only the binary differs",
            "nothing is tuned toward a published temperature",
        ],
        "calls": calls,
        "sizing": {
            "cost_model": COST,
            "declared": all_tiers,
            "tier_A_ready_now": tier(ready),
            "tier_B_blocked_on_SLAB_048": tier(blocked),
            "reserves_cpu_s": round(reserve, 2),
            "total_conservative_cpu_s": round(total, 2),
            "total_conservative_cpu_min": round(total / 60, 2),
        },
        "grant_request": {
            "solver_executions_declared": len(calls),
            "solver_executions_max_including_reserves": (len(calls) + COST["retry_reserve_calls"]
                                                         + COST["timeout_reserve_calls"]),
            "cpu_cap_minutes": math.ceil(1.2 * total / 60),
            "cpu_cap_rule": "ceil(1.2 x total_conservative_cpu_s / 60)",
            "cpu_cap_scope": "solver executions, worker start/reap and archiving; HotSpot builds are separate",
            "concurrency": 1,
            "proposed_expiry_utc": "2026-11-01T12:00:00Z",
            "tier_B_condition": "runs only if SLAB-048's 45 mm fixture and reference data merge before expiry",
            "gpu": False,
            "host": "the Azure x86_64 host that produced the mesh and TIMING evidence",
        },
    }


# ----------------------------------------------------------------------------------------------
# After a granted run: the per-call record (astra #56701)
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
                         expected_package: dict | None = None) -> dict:
    directory = Path(directory)
    files = {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
             for path in sorted(directory.iterdir()) if path.is_file()}
    package = read_hotspot_config(directory / config)
    package_record = {name: package.get(name) for name in ("s_spreader", "s_sink", "r_convec", "t_spreader",
                                                           "k_spreader", "t_sink", "k_sink", "ambient",
                                                           "model_secondary")}
    package_ok = None
    if expected_package is not None:
        package_ok = (math.isclose(float(package["s_spreader"]), expected_package["s_spreader_m"], rel_tol=1e-12)
                      and math.isclose(float(package["s_sink"]), expected_package["s_sink_m"], rel_tol=1e-12)
                      and math.isclose(float(package["r_convec"]), expected_package["r_convec_K_per_W"], rel_tol=1e-12))
    layers = read_lcf(directory / lcf, directory)
    temperatures = read_grid(directory / grid)
    cells = len(temperatures[0])
    n = int(round(math.sqrt(cells)))
    if n * n != cells or set(temperatures) != set(range(len(layers) + 2)):
        raise ValueError("grid output does not cover every layer on a square grid")
    width, height = total_extent(read_flp(layers[0]["flp"]))
    power_layers = [layer["layer"] for layer in layers if layer["power"]]
    if len(power_layers) != 1:
        raise ValueError("expected exactly one powered layer")
    active = power_layers[0]
    values = temperatures[active]
    peak = max(values)
    argmax = [{"row": index // n, "col": index % n} for index, value in enumerate(values) if value == peak]

    def center_value(layer: int, unit: dict) -> tuple[float, list[dict]]:
        mapped = center_cells(block_extent(unit, width, height, n, n))
        total = sum(temperatures[layer][c["row"] * n + c["col"]] * c["weight"] for c in mapped)
        return total, mapped

    chiplets = []
    for unit in read_flp(layers[active]["flp"]):
        if re.fullmatch(chiplet_pattern, unit["name"]):
            value, mapped = center_value(active, unit)
            chiplets.append({"name": unit["name"], "center_K": value, "center_C": value - KELVIN_OFFSET,
                             "cells": mapped, "distinct_cells": len(mapped)})
    if not chiplets:
        raise ValueError("no chiplet blocks matched")

    # HotSpot 6.0 stdout: "Unit Steady(Kelvin)" then dump_temp (every block of every layer, centre-mapped in
    # TAP's config, then the package nodes). TAP takes max(float(tokens[3::2])) - 273.15.
    emulated = []
    package_layers = (len(layers), len(layers) + 1)
    for layer in [*range(len(layers)), *package_layers]:
        floorplan = layers[min(layer, len(layers) - 1)]["flp"]
        for unit in read_flp(floorplan):
            value, _ = center_value(layer, unit)
            emulated.append((f"layer{layer}:{unit['name']}", value))
    emulated.extend((name, value) for name, value in read_steady(directory / steady) if name.startswith("inode_"))
    selector_name, selector_value = max(emulated, key=lambda item: item[1])
    literal = {"applicable": False, "value_c": None}
    if stdout and (directory / stdout).is_file():
        tokens = (directory / stdout).read_text(encoding="utf-8", errors="replace").split()
        try:
            literal = {"applicable": True, "value_c": max(map(float, tokens[3::2])) - KELVIN_OFFSET}
        except ValueError as exc:
            literal = {"applicable": False, "value_c": None,
                       "reason": f"HotSpot 7 prints no temperatures to stdout ({type(exc).__name__})"}
    return {
        "schema": "sentilab-slab049-call-record-v1",
        "files": files,
        "output_precision": {"grid_decimals_K": _decimals(directory / grid),
                             "steady_decimals_K": _decimals(directory / steady)},
        "package_from_actual_config": package_record,
        "package_matches_fixture": package_ok,
        "grid": n,
        "active_layer": active,
        "layer4_grid_peak_K": peak,
        "layer4_grid_peak_C": peak - KELVIN_OFFSET,
        "layer4_grid_argmax": argmax,
        "chiplet_centers": chiplets,
        "max_chiplet_center_C": max(c["center_C"] for c in chiplets),
        "tap_stdout_selector_literal": literal,
        "tap_stdout_selector_emulated_hotspot6": {"value_C": selector_value - KELVIN_OFFSET, "argmax": selector_name,
                                                  "note": "computed from %.2f K grid cells, so within 0.01 K of "
                                                          "HotSpot's own centre mapping"},
    }


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
    for name in ("analytic", "slab", "call-list"):
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
    if args.command == "slab":
        status = 0
        files = slab_files()
        sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
        for name, data in sorted(files.items()):
            status |= _write_or_check(target / "slab" / name, data, check)
        status |= _write_or_check(target / "slab" / "SHA256SUMS", sums.encode("ascii"), check)
        return status
    return _write_or_check(target / "CALL-LIST.json", _dump(build_call_list()), check)


if __name__ == "__main__":
    raise SystemExit(main())
