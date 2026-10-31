"""Persistent isolated TAP worker; each request launches one bounded HotSpot process."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time


_MODULE_STARTED = time.perf_counter()
_STARTUP_ACCOUNTED = False

TAP_ROOT = Path(__file__).resolve().parent.parent / "sundai_tap"
HOTSPOT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = HOTSPOT_ROOT.parent
if str(TAP_ROOT) not in sys.path:
    sys.path.insert(0, str(TAP_ROOT))
from passive_interposer import PassiveInterposer  # noqa: E402


@contextmanager
def _output_directory(workspace_root, retained_root=None):
    if retained_root is None:
        with tempfile.TemporaryDirectory(prefix='tfl-hotspot-', dir=workspace_root) as directory:
            yield directory
        return
    if not isinstance(retained_root, str) or not Path(retained_root).is_absolute():
        raise ValueError('retained output root must be an absolute parent-owned directory')
    root = Path(retained_root).resolve(strict=True)
    # Only the parent supplies this path; use a fresh child, never a caller-supplied filename.
    directory = Path(tempfile.mkdtemp(prefix='evaluation-', dir=root)).resolve()
    directory.relative_to(root)
    yield str(directory)


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


def _retain_solver_output(output, stdout, stderr, status):
    """Keep original bytes as well as readable text, including timeout payloads."""
    for name, value in (('stdout', stdout), ('stderr', stderr)):
        binary = output / f'{name}.bin'
        status[f'{name}_payload_type'] = type(value).__name__
        if value is None:
            data = binary.read_bytes() if binary.exists() else b''
        else:
            data = value if isinstance(value, bytes) else value.encode('utf-8')
        binary.write_bytes(data)
        (output / f'{name}.txt').write_text(data.decode('utf-8', errors='replace'), encoding='utf-8')
        status[f'{name}_bytes'] = len(data)
    (output / 'EXIT.json').write_text(json.dumps(status) + '\n', encoding='utf-8')


def _cpu_seconds() -> float:
    return sum(usage.ru_utime + usage.ru_stime for usage in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def _worker_startup() -> dict:
    global _STARTUP_ACCOUNTED
    if _STARTUP_ACCOUNTED:
        return {'cpu_seconds': 0.0, 'wall_seconds': 0.0}
    _STARTUP_ACCOUNTED = True
    usage = resource.getrusage(resource.RUSAGE_SELF)
    try:
        # stat field 22 follows the parenthesized comm field; comm may contain spaces.
        fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        start_seconds = int(fields[19]) / os.sysconf('SC_CLK_TCK')
        wall_seconds = time.clock_gettime(time.CLOCK_BOOTTIME) - start_seconds
    except (OSError, ValueError, AttributeError, IndexError):
        wall_seconds = time.perf_counter() - _MODULE_STARTED
    return {'cpu_seconds': usage.ru_utime + usage.ru_stime,
            'wall_seconds': max(0.0, wall_seconds)}


class _PhaseTimings:
    def __init__(self):
        self.values = {name: {'cpu_seconds': 0.0, 'wall_seconds': 0.0}
                       for name in ('generate', 'solve', 'archive')}
        self.values['worker_startup'] = _worker_startup()
        self.active = 'generate'
        self.cpu, self.wall = _cpu_seconds(), time.perf_counter()

    def switch(self, name):
        cpu, wall = _cpu_seconds(), time.perf_counter()
        if self.active is not None:
            phase = self.values[self.active]
            phase['cpu_seconds'] += max(0.0, cpu - self.cpu)
            phase['wall_seconds'] += max(0.0, wall - self.wall)
        self.active, self.cpu, self.wall = name, cpu, wall

    def checkpoint(self, output, status, active_phase=None):
        self.switch(self.active)
        path = output / 'PHASES.json'
        temporary = output / 'PHASES.json.tmp'
        temporary.write_text(json.dumps({'schema_version': 1, 'status': status,
                                        'active_phase': active_phase or self.active,
                                        'phase_timings': self.values}, sort_keys=True) + '\n')
        temporary.replace(path)


def generate_inputs(output: Path, *, size, granularity, widths, heights, powers, connections, link_type,
                    halos, points, rotated) -> None:
    """Write TAP's floorplans, power trace and HotSpot config for one layout. Runs no solver.

    TAP reads util/hotspot.config relative to the working directory, so call this from TAP_ROOT.
    """
    system = PassiveInterposer()
    system.set_chiplet_count(len(widths))
    system.initialize()
    system.set_interposer_size(size)
    system.set_chiplet_size(list(widths), list(heights))
    system.set_chiplet_power(list(powers))
    system.set_connection_matrix([list(row) for row in connections])
    system.set_granularity(granularity)
    system.set_link_type(link_type)
    system.compute_ubump_overhead()
    if any(not math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-12)
           for actual, expected in zip(system.hubump, halos)):
        raise ValueError("TAP microbump halos differ from the problem contract")
    # TAP's own rotate swaps a die's width and height; the halo depends on the perimeter only.
    for index, turned in enumerate(rotated):
        if turned:
            system.rotate(index)
    system.set_path(str(output) + os.sep)
    system.x = [point[0] for point in points]
    system.y = [point[1] for point in points]
    system.gen_flp("sample")
    system.gen_ptrace("sample")


def evaluate(request: dict) -> dict:
    phases = _PhaseTimings()
    workspace_root = request.get('workspace_root')
    if not isinstance(workspace_root, str) or not workspace_root or not Path(workspace_root).is_dir():
        # Preserve request-validation precedence when there is nowhere to archive.
        # _evaluate rejects the workspace before generating any native inputs.
        return _evaluate(request, None, False, phases)
    retained = request.get('retained_output_root') is not None
    with _output_directory(Path(workspace_root), request.get('retained_output_root')) as directory:
        output = Path(directory)
        result = None
        status = 'error'
        try:
            if retained:
                phases.switch('archive')
                (output / 'REQUEST.json').write_text(json.dumps(request, sort_keys=True) + '\n')
                phases.checkpoint(output, 'generating', 'generate')
                phases.switch('generate')
            result = _evaluate(request, output, retained, phases)
            status = 'complete'
            return result
        except Exception as exc:
            phases.switch('archive')
            if retained:
                (output / 'ERROR.json').write_text(json.dumps({
                    'error_type': type(exc).__name__, 'error': str(exc)}) + '\n')
                if not (output / 'EXIT.json').exists():
                    _retain_solver_output(output, None, None,
                                          {'status': 'worker_error', 'returncode': None})
            exc.phase_timings = phases.values
            exc.raw_output_directory = str(output) if retained else None
            raise
        finally:
            phases.switch('archive')
            if retained:
                artifacts = {path.name: _sha256(path) for path in sorted(output.iterdir())
                             if path.is_file() and path.name not in {'PHASES.json', 'ARTIFACTS.json'}}
                (output / 'ARTIFACTS.json').write_text(json.dumps(artifacts, sort_keys=True) + '\n')
            phases.switch(None)
            if result is not None:
                result['phase_timings'] = phases.values
                result['raw_output_directory'] = str(output) if retained else None
            if retained:
                phases.checkpoint(output, status)


def _evaluate(request: dict, output: Path | None, retained: bool, phases: _PhaseTimings) -> dict:
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
    if not isinstance(centers, list) or len(centers) == 0:
        raise ValueError("TAP fixture requires at least one chiplet center")
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
    count = len(widths)
    if (size <= 0 or granularity <= 0 or len(points) != count or len(heights) != count or len(powers) != count or
            len(halos) != count or len(connections) != count or any(len(row) != count for row in connections) or
            not isinstance(parameters["link_type"], str)):
        raise ValueError("TAP fixture parameters are inconsistent")
    # Absent means the configured orientation for every die (requests that predate rotation).
    rotated = request.get("rotated", [False] * count)
    if not isinstance(rotated, list) or len(rotated) != count or any(not isinstance(flag, bool) for flag in rotated):
        raise ValueError("TAP rotation flags are malformed")

    workspace_root = request.get('workspace_root')
    if not isinstance(workspace_root, str) or not workspace_root:
        raise ValueError('parent-owned workspace path is missing')
    if output is None:
        raise ValueError('parent-owned workspace is unavailable')

    # The worker starts in TAP_ROOT for the legacy generator's relative config.
    started_generation = time.perf_counter()
    generate_inputs(output, size=size, granularity=granularity, widths=widths, heights=heights,
                    powers=powers, connections=connections, link_type=parameters["link_type"],
                    halos=halos, points=points, rotated=rotated)
    generation_seconds = time.perf_counter() - started_generation

    config = output / "new_hotspot.config"
    floorplan = output / "sampleL4_ChipLayer.flp"
    trace = output / "sample.ptrace"
    steady = output / "sample.steady"
    grid = output / "sample.grid.steady"
    layers = output / "samplelayers.lcf"
    input_paths = tuple(sorted(path for path in output.iterdir()
                              if path.is_file() and path.name not in {'REQUEST.json', 'PHASES.json'}))
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
    # The native process receives exactly this environment, never inherited secrets.
    environment = {'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC'}
    phases.switch('archive')
    if retained:
        (output / 'COMMAND.json').write_text(json.dumps({
            'command': command, 'cwd': str(HOTSPOT_ROOT), 'environment': environment},
            sort_keys=True) + '\n')
        (output / 'IDENTITIES.json').write_text(json.dumps({
            'binary_sha256': binary_sha256, 'source_sha256': expected_sources,
            'image_identity': request.get('image_identity'),
            'candidate_hash': candidate_hash, 'problem_hash': problem_hash},
            sort_keys=True) + '\n')
        (output / 'INPUTS.json').write_text(json.dumps(input_hashes, sort_keys=True) + '\n')
        phases.checkpoint(output, 'solving', 'solve')
    phases.switch('solve')
    solver_started = time.perf_counter()
    # File-backed streams survive a parent-enforced worker/process-group kill.
    from contextlib import ExitStack
    try:
        with ExitStack() as streams:
            outputs = ({name: streams.enter_context((output / f'{name}.bin').open('wb'))
                        for name in ('stdout', 'stderr')} if retained else {'capture_output': True})
            process = subprocess.run(command, cwd=HOTSPOT_ROOT, text=True,
                                     timeout=timeout, check=False, env=environment, **outputs)
    except subprocess.TimeoutExpired as exc:
        phases.switch('archive')
        if retained:
            _retain_solver_output(output, exc.stdout, exc.stderr,
                                  {'status': 'timeout', 'returncode': None, 'command': command,
                                   'timeout_s': timeout,
                                   'elapsed_s': time.perf_counter() - solver_started})
            (output / 'TIMEOUT.txt').write_text(str(exc))
        raise TimeoutError(f"TFL_ORACLE_TIMEOUT HotSpot exceeded {timeout:g} seconds") from exc
    finally:
        phases.switch('archive')
    solver_seconds = time.perf_counter() - solver_started
    if retained:
        _retain_solver_output(output, process.stdout, process.stderr,
                              {'status': 'exited', 'returncode': process.returncode, 'command': command})
    if process.returncode != 0:
        stdout = (output / 'stdout.txt').read_text() if retained else process.stdout
        stderr = (output / 'stderr.txt').read_text() if retained else process.stderr
        detail = (stderr + "\n" + stdout)[-4000:].strip()
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
                "phase_timings": getattr(exc, 'phase_timings', {}),
                "raw_output_directory": getattr(exc, 'raw_output_directory', None),
            }
            print(json.dumps(response, separators=(",", ":")), flush=True)
            return 1
        print(json.dumps({"ok": True, "result": result}, separators=(",", ":"), allow_nan=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
