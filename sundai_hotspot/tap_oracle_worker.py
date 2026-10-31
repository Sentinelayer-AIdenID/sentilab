"""Persistent isolated TAP worker; each request launches one bounded HotSpot process."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


TAP_ROOT = Path(__file__).resolve().parent.parent / "sundai_tap"
HOTSPOT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = HOTSPOT_ROOT.parent
if str(TAP_ROOT) not in sys.path:
    sys.path.insert(0, str(TAP_ROOT))
from passive_interposer import PassiveInterposer  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _parse_grid(path: Path, rows: int, cols: int) -> tuple[tuple[tuple[float, ...], ...], float]:
    layers: dict[int, list[float]] = {}
    current_layer = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Layer "):
            match = re.fullmatch(r"Layer\s+(\d+):", stripped)
            if not match:
                raise ValueError(f"invalid grid layer header at line {line_number}")
            current_layer = int(match.group(1))
            if current_layer in layers:
                raise ValueError(f"duplicate grid layer {current_layer}")
            layers[current_layer] = []
            continue
        if current_layer is None:
            raise ValueError(f"grid value before layer header at line {line_number}")
        fields = stripped.split()
        if len(fields) != 2:
            raise ValueError(f"invalid grid cell at line {line_number}")
        index = int(fields[0])
        value = _finite_number(float(fields[1]), "grid temperature")
        if value <= 0:
            raise ValueError(f"grid temperature must be positive Kelvin at line {line_number}")
        values = layers[current_layer]
        if index != len(values):
            raise ValueError(f"non-sequential grid index at line {line_number}")
        values.append(value)

    if set(layers) != set(range(8)):
        raise ValueError("HotSpot did not return all eight TAP layers")
    expected_cells = rows * cols
    for layer, values in layers.items():
        if len(values) != expected_cells:
            raise ValueError(
                f"HotSpot layer {layer} has {len(values)} cells; expected {expected_cells}"
            )
    values = layers[4]
    heatmap = tuple(tuple(values[offset:offset + cols]) for offset in range(0, expected_cells, cols))
    return heatmap, max(max(layer) for layer in layers.values())


def _request(raw: bytes) -> dict:
    if len(raw) > 65536:
        raise ValueError("oracle request exceeds 64 KiB")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("oracle request must be an object")
    return value


def evaluate(request: dict) -> dict:
    requested_binary = request.get("hotspot_binary")
    if not isinstance(requested_binary, str) or not requested_binary:
        raise ValueError("HotSpot binary path is missing")
    hotspot_binary = Path(requested_binary).resolve()
    if not hotspot_binary.is_file():
        raise FileNotFoundError(f"HotSpot binary is not built: {hotspot_binary}")
    expected_binary_sha256 = request.get("expected_binary_sha256")
    binary_sha256 = _sha256(hotspot_binary)
    if expected_binary_sha256 != binary_sha256:
        raise ValueError("HotSpot binary changed after the problem contract was created")
    expected_sources = request.get("expected_source_sha256")
    if not isinstance(expected_sources, dict) or not expected_sources:
        raise ValueError("problem source hashes are missing")
    for relative_path, expected_sha256 in expected_sources.items():
        if (not isinstance(relative_path, str) or not isinstance(expected_sha256, str) or
                not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
            raise ValueError("problem source hash is malformed")
        source_path = (REPO_ROOT / relative_path).resolve()
        if not source_path.is_relative_to(REPO_ROOT) or not source_path.is_file():
            raise ValueError("problem source path is invalid")
        if _sha256(source_path) != expected_sha256:
            raise ValueError(f"problem source changed during oracle run: {relative_path}")

    candidate_hash = request.get("candidate_hash")
    problem_hash = request.get("problem_hash")
    if not isinstance(candidate_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", candidate_hash):
        raise ValueError("invalid candidate hash")
    if not isinstance(problem_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", problem_hash):
        raise ValueError("invalid problem hash")

    rows = request.get("grid_rows")
    cols = request.get("grid_cols")
    if (isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 128 or
            isinstance(cols, bool) or not isinstance(cols, int) or not 1 <= cols <= 128):
        raise ValueError("invalid HotSpot grid dimensions")
    timeout = _finite_number(request.get("solver_timeout_s"), "solver timeout")
    if timeout <= 0:
        raise ValueError("solver timeout must be positive")

    centers = request.get("centers_mm")
    if not isinstance(centers, list) or len(centers) != 6:
        raise ValueError("TAP Ascend910 requires six chiplet centers")
    points = []
    for index, point in enumerate(centers):
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"invalid center for chiplet {index}")
        points.append(tuple(_finite_number(value, f"chiplet {index} center") for value in point))

    parameters = request.get("tap_parameters")
    required_parameters = {
        "interposer_size_mm", "widths_mm", "heights_mm", "powers_w", "connections",
        "link_type", "granularity_mm", "bump_halos_mm", "ambient_c",
    }
    if not isinstance(parameters, dict) or set(parameters) != required_parameters:
        raise ValueError("TAP parameters are missing or malformed")
    size = _finite_number(parameters["interposer_size_mm"], "interposer size")
    granularity = _finite_number(parameters["granularity_mm"], "placement granularity")
    ambient_c = _finite_number(parameters["ambient_c"], "ambient temperature")
    widths = tuple(_finite_number(value, "chiplet width") for value in parameters["widths_mm"])
    heights = tuple(_finite_number(value, "chiplet height") for value in parameters["heights_mm"])
    powers = tuple(_finite_number(value, "chiplet power") for value in parameters["powers_w"])
    halos = tuple(_finite_number(value, "microbump halo") for value in parameters["bump_halos_mm"])
    connections = tuple(tuple(_finite_number(value, "connection weight") for value in row)
                        for row in parameters["connections"])
    if (size <= 0 or granularity <= 0 or len(widths) != 6 or len(heights) != 6 or len(powers) != 6 or
            len(halos) != 6 or len(connections) != 6 or any(len(row) != 6 for row in connections) or
            not isinstance(parameters["link_type"], str)):
        raise ValueError("TAP Ascend910 parameters are inconsistent")

    # TAP's legacy generator reads util/hotspot.config relative to the process
    # startup directory. The worker is launched with TAP_ROOT as cwd; no chdir
    # mutates process-global state, and each call receives a fresh output tree
    # under the parent-owned workspace so timeout cleanup is reliable.
    workspace_root = request.get("workspace_root")
    if not isinstance(workspace_root, str) or not workspace_root:
        raise ValueError("parent-owned workspace path is missing")
    workspace_root = Path(workspace_root).resolve()
    if not workspace_root.is_dir():
        raise ValueError("parent-owned workspace is unavailable")
    started_generation = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="tfl-hotspot-", dir=workspace_root) as directory:
        output = Path(directory)
        system = PassiveInterposer()
        system.set_chiplet_count(len(widths))
        system.initialize()
        system.set_interposer_size(size)
        system.set_chiplet_size(list(widths), list(heights))
        system.set_chiplet_power(list(powers))
        system.set_connection_matrix([list(row) for row in connections])
        system.set_granularity(granularity)
        system.set_link_type(parameters["link_type"])
        system.compute_ubump_overhead()
        if any(not math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-12)
               for actual, expected in zip(system.hubump, halos)):
            raise ValueError("TAP microbump halos differ from the problem contract")
        system.set_path(str(output) + os.sep)
        system.x = [point[0] for point in points]
        system.y = [point[1] for point in points]
        system.gen_flp("sample")
        system.gen_ptrace("sample")
        generation_seconds = time.perf_counter() - started_generation

        config = output / "new_hotspot.config"
        floorplan = output / "sampleL4_ChipLayer.flp"
        trace = output / "sample.ptrace"
        steady = output / "sample.steady"
        grid = output / "sample.grid.steady"
        layers = output / "samplelayers.lcf"
        input_paths = tuple(sorted(path for path in output.iterdir() if path.is_file()))
        input_hashes = {path.name: _sha256(path) for path in input_paths}
        layer_references = {
            Path(line.strip()).name
            for line in layers.read_text(encoding="utf-8").splitlines()
            if line.strip().endswith(".flp")
        }
        if not layer_references or not layer_references.issubset(input_hashes):
            raise RuntimeError("TAP layer config references an unhashed generated floorplan")
        command = [
            str(hotspot_binary),
            "-c", str(config),
            "-f", str(floorplan),
            "-p", str(trace),
            "-steady_file", str(steady),
            "-grid_steady_file", str(grid),
            "-model_type", "grid",
            "-detailed_3D", "on",
            "-grid_layer_file", str(layers),
            "-grid_rows", str(rows),
            "-grid_cols", str(cols),
            "-grid_map_mode", "max",
        ]
        solver_started = time.perf_counter()
        try:
            process = subprocess.run(
                command,
                cwd=HOTSPOT_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"TFL_ORACLE_TIMEOUT HotSpot exceeded {timeout:g} seconds") from exc
        solver_seconds = time.perf_counter() - solver_started
        if process.returncode != 0:
            detail = (process.stderr + "\n" + process.stdout)[-4000:].strip()
            raise RuntimeError(f"HotSpot exited {process.returncode}: {detail}")
        if not grid.is_file() or grid.stat().st_size == 0:
            raise RuntimeError("HotSpot completed without a grid steady-state file")

        heatmap, all_layers_peak = _parse_grid(grid, rows, cols)
        return {
            "candidate_hash": candidate_hash,
            "problem_hash": problem_hash,
            "binary_sha256": binary_sha256,
            "grid_rows": rows,
            "grid_cols": cols,
            "ambient_c": ambient_c,
            "heatmap_c": [[cell - 273.15 for cell in row] for row in heatmap],
            "maximum_temperature_c": max(max(row) for row in heatmap) - 273.15,
            "all_layers_peak_c": all_layers_peak - 273.15,
            "solver_seconds": solver_seconds,
            "input_generation_seconds": generation_seconds,
            "input_sha256": input_hashes,
        }


def main() -> int:
    # The parent leases this process to one request at a time. Each request
    # still gets a fresh output TemporaryDirectory, and evaluate() re-hashes
    # the binary and every generator source before starting HotSpot.
    while True:
        raw = sys.stdin.buffer.readline(65538)
        if not raw:
            return 0
        if len(raw) > 65537 or not raw.endswith(b"\n"):
            response = {"ok": False, "error_type": "ValueError", "error": "oracle request exceeds 64 KiB or is not line terminated"}
            print(json.dumps(response, separators=(",", ":")), flush=True)
            return 1
        try:
            request = _request(raw[:-1])
            result = evaluate(request)
        except Exception as exc:  # one failed request poisons this worker; the parent replaces it
            response = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": f"{type(exc).__name__}: {exc}"[-2000:],
            }
            print(json.dumps(response, separators=(",", ":")), flush=True)
            return 1
        print(json.dumps({"ok": True, "result": result}, separators=(",", ":"), allow_nan=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
