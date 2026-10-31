"""Warm isolated-worker HotSpot adapter for the TAP-2.5D Ascend910 design."""
from __future__ import annotations

import asyncio
import configparser
from contextlib import asynccontextmanager
import hashlib
import json
import math
import numbers
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TAP_ROOT = REPO_ROOT / "sundai_tap"
HOTSPOT_ROOT = REPO_ROOT / "sundai_hotspot"
TAP_CONFIG_DEFAULT_ID = "ascend910"
TAP_CONFIGS = {
    "ascend910": TAP_ROOT / "configs" / "sys_ascend910.cfg",
    "micro150": TAP_ROOT / "configs" / "sys_micro150.cfg",
    # The TAP-2.5D paper's 45 mm frame (SLAB-048). Same dies and package recipe; the frame and
    # the [sentilab] legality rules in each file are what differ from the 50 mm fixtures above.
    "ascend910-45mm": TAP_ROOT / "configs" / "sys_ascend910_45mm.cfg",
    "micro150-45mm": TAP_ROOT / "configs" / "sys_micro150_45mm.cfg",
}
# TAP draws g/2-wide edge strips (g = 1 mm) round the interposer; every die keeps its halo clear of them.
TAP_MARGIN_MM = 0.5
SENTILAB_RULES_SECTION = "sentilab"
ROTATION_MODES = ("catalog", "per_die_90")
TAP_HOTSPOT_CONFIG = TAP_ROOT / "util" / "hotspot.config"
HOTSPOT_BINARY = HOTSPOT_ROOT / "hotspot"
WORKER = HOTSPOT_ROOT / "tap_oracle_worker.py"
MAX_WORKER_REQUEST_BYTES = 64 * 1024
MAX_WORKER_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_WORKERS = 8

# TAP imports its sibling modules as top-level names and computes the bump
# halos in PassiveInterposer. Keep its source tree first for those imports.
if str(TAP_ROOT) in sys.path:
    sys.path.remove(str(TAP_ROOT))
sys.path.insert(0, str(TAP_ROOT))
from passive_interposer import PassiveInterposer  # noqa: E402

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from sundai_controller.controller import Chiplet, Design, ThermalResult  # noqa: E402


class TapLegalityError(ValueError):
    """A design violates the TAP benchmark geometry or placement grid."""


class HotSpotOracleError(RuntimeError):
    """HotSpot did not produce a complete, valid thermal result."""


class HotSpotTimeoutError(HotSpotOracleError):
    """The isolated evaluator exceeded its bounded runtime."""


@dataclass(frozen=True)
class HotSpotThermalResult(ThermalResult):
    """Controller result plus a Manhattan center-distance wire proxy and chip heatmap."""

    @property
    def evaluator_version(self) -> str:
        return self.solver_version

    wirelength_mm: float = field(kw_only=True)
    wire_metric: str = field(kw_only=True)
    heatmap_c: tuple[tuple[float, ...], ...] = field(kw_only=True)
    grid_rows: int = field(kw_only=True)
    grid_cols: int = field(kw_only=True)
    ambient_c: float = field(kw_only=True)
    solver_seconds: float = field(kw_only=True)
    evaluation_seconds: float = field(kw_only=True)
    input_generation_seconds: float = field(kw_only=True)
    input_sha256: tuple[tuple[str, str], ...] = field(kw_only=True)
    all_layers_peak_c: float = field(kw_only=True)
    fixture_id: str = field(kw_only=True)
    config_sha256: str = field(kw_only=True)


@dataclass(frozen=True)
class TapProblem:
    fixture_id: str
    interposer_size_mm: float
    widths_mm: tuple[float, ...]
    heights_mm: tuple[float, ...]
    powers_w: tuple[float, ...]
    connections: tuple[tuple[float, ...], ...]
    link_type: str
    granularity_mm: float
    bump_halos_mm: tuple[float, ...]
    ambient_c: float
    config_sha256: str
    hotspot_config_sha256: str
    tap_upstream_commit: str
    hotspot_upstream_commit: str
    hotspot_binary_sha256: str
    generator_sha256: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TapLegality:
    """SentiLab placement rules on top of the TAP problem; TapProblem keeps only the physics inputs.

    The 50 mm fixtures declare no rules and keep their historical defaults: the 1 mm TAP grid,
    catalog orientation only and halo clearance as the only spacing rule.
    """

    margin_mm: float
    center_lattice_mm: float | None
    min_die_gap_mm: float
    rotation: str
    # Allowed (width, height) footprints per die, in die order; a turned die swaps the pair.
    orientation_catalog_mm: tuple[tuple[tuple[float, float], ...], ...]


@dataclass(frozen=True)
class LayoutViolation:
    """One placement-rule miss: rule is margin, lattice, halo_overlap or min_spacing."""

    rule: str
    dies: tuple[int, ...]
    amount_mm: float
    message: str


def _same_mm(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-9)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_upstream_commit(path: Path) -> str:
    value = _read_text(path).strip()
    if not value or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise HotSpotOracleError(f"invalid upstream commit marker: {path.name}")
    return value.lower()


def _parse_float_list(value: str, label: str) -> tuple[float, ...]:
    try:
        values = tuple(float(item.strip()) for item in value.replace("\n", "").split(",") if item.strip())
    except ValueError as exc:
        raise HotSpotOracleError(f"invalid TAP {label}") from exc
    if not values or not all(math.isfinite(item) for item in values):
        raise HotSpotOracleError(f"invalid TAP {label}")
    return values


def _load_problem(*, config_path: Path = TAP_CONFIGS[TAP_CONFIG_DEFAULT_ID],
                  hotspot_binary: Path | None = HOTSPOT_BINARY) -> TapProblem:
    """Load the TAP problem. hotspot_binary=None gives a geometry-only problem with no solver identity."""
    if not config_path.is_file() or not TAP_HOTSPOT_CONFIG.is_file():
        raise HotSpotOracleError(f"TAP fixture configuration is missing: {config_path}")
    if hotspot_binary is not None and not hotspot_binary.is_file():
        raise HotSpotOracleError(f"HotSpot binary is not built: {hotspot_binary}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(_read_text(config_path))
    count = parser.getint("chiplets", "chiplet_count")
    widths = _parse_float_list(parser.get("chiplets", "widths"), "widths")
    heights = _parse_float_list(parser.get("chiplets", "heights"), "heights")
    powers = _parse_float_list(parser.get("chiplets", "powers"), "powers")
    rows = parser.get("chiplets", "connections").split(";")
    try:
        connections = tuple(tuple(float(value.strip()) for value in row.split(",") if value.strip())
                            for row in rows if row.strip())
        connections = tuple(tuple(float(value) for value in row) for row in connections)
        size = parser.getfloat("interposer", "intp_size")
        granularity = parser.getfloat("general", "placer_granularity", fallback=1.0)
        link_type = parser.get("interposer", "link_type", fallback="nppl")
    except (ValueError, configparser.Error) as exc:
        raise HotSpotOracleError("invalid TAP fixture configuration") from exc
    if (count != len(widths) or count != len(heights) or count != len(powers) or
            len(connections) != count or any(len(row) != count for row in connections) or
            not math.isfinite(size) or size <= 0 or not math.isfinite(granularity) or granularity <= 0):
        raise HotSpotOracleError("inconsistent TAP fixture configuration")

    ambient_kelvin = None
    for line in _read_text(TAP_HOTSPOT_CONFIG).splitlines():
        parts = line.split()
        if parts and parts[0] == "-ambient" and len(parts) == 2:
            ambient_kelvin = float(parts[1])
            break
    if ambient_kelvin is None or not math.isfinite(ambient_kelvin) or ambient_kelvin <= 0:
        raise HotSpotOracleError("TAP HotSpot config has no valid ambient temperature")

    system = PassiveInterposer()
    system.set_chiplet_count(count)
    system.initialize()
    system.set_link_type(link_type)
    system.set_chiplet_size(list(widths), list(heights))
    system.set_connection_matrix([list(row) for row in connections])
    system.compute_ubump_overhead()
    bump_halos = tuple(float(value) for value in system.hubump)

    generator_paths = (
        config_path,
        TAP_HOTSPOT_CONFIG,
        TAP_ROOT / "UPSTREAM_COMMIT",
        HOTSPOT_ROOT / "UPSTREAM_COMMIT",
        TAP_ROOT / "passive_interposer.py",
        TAP_ROOT / "system.py",
        TAP_ROOT / "init_placement.py",
        TAP_ROOT / "block_occupation.py",
        TAP_ROOT / "fastSA.py",
        TAP_ROOT / "bstree.py",
        TAP_ROOT / "util" / "fill_space.py",
        Path(__file__).resolve(),
        WORKER,
    )
    generators = tuple((path.relative_to(REPO_ROOT).as_posix(), _sha256(path)) for path in generator_paths)
    fixture_id = next(
        (fixture_id for fixture_id, fixture_path in TAP_CONFIGS.items() if fixture_path.resolve() == config_path.resolve()),
        None,
    )
    if fixture_id is None:
        raise HotSpotOracleError(f"unknown TAP fixture for config path: {config_path}")
    return TapProblem(
        fixture_id=fixture_id,
        interposer_size_mm=size,
        widths_mm=widths,
        heights_mm=heights,
        powers_w=powers,
        connections=connections,
        link_type=link_type,
        granularity_mm=granularity,
        bump_halos_mm=bump_halos,
        ambient_c=ambient_kelvin - 273.15,
        config_sha256=_sha256(config_path),
        hotspot_config_sha256=_sha256(TAP_HOTSPOT_CONFIG),
        tap_upstream_commit=_read_upstream_commit(TAP_ROOT / "UPSTREAM_COMMIT"),
        hotspot_upstream_commit=_read_upstream_commit(HOTSPOT_ROOT / "UPSTREAM_COMMIT"),
        hotspot_binary_sha256="" if hotspot_binary is None else _sha256(hotspot_binary),
        generator_sha256=generators,
    )


def _load_legality(config_path: Path, problem: TapProblem) -> TapLegality:
    """Read the optional [sentilab] section; anything unknown or malformed fails closed."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(_read_text(config_path))
    rules = dict(parser.items(SENTILAB_RULES_SECTION)) if parser.has_section(SENTILAB_RULES_SECTION) else {}
    unknown = set(rules) - {"center_lattice_mm", "min_die_gap_mm", "rotation"}
    if unknown:
        raise HotSpotOracleError(f"unknown SentiLab fixture rule: {sorted(unknown)}")
    try:
        lattice = float(rules.get("center_lattice_mm", problem.granularity_mm))
        min_gap = float(rules.get("min_die_gap_mm", 0.0))
    except ValueError as exc:
        raise HotSpotOracleError("invalid SentiLab fixture rule") from exc
    rotation = rules.get("rotation", "catalog")
    if (not math.isfinite(lattice) or lattice <= 0 or not math.isfinite(min_gap) or min_gap < 0 or
            rotation not in ROTATION_MODES):
        raise HotSpotOracleError("invalid SentiLab fixture rule")
    # A square die has one footprint, so a turn never gives it a second catalog entry.
    catalog = tuple(((w, h),) if rotation == "catalog" or w == h else ((w, h), (h, w))
                    for w, h in zip(problem.widths_mm, problem.heights_mm))
    return TapLegality(TAP_MARGIN_MM, lattice, min_gap, rotation, catalog)


class TapGeometry:
    """A fixture's geometry and legality. Needs no HotSpot binary; HotSpotOracle delegates here."""

    def __init__(self, problem: TapProblem, legality: TapLegality):
        self.problem = problem
        self.legality = legality

    @classmethod
    def load(cls, fixture: str = TAP_CONFIG_DEFAULT_ID) -> "TapGeometry":
        if not isinstance(fixture, str) or fixture not in TAP_CONFIGS:
            raise ValueError(f"fixture must be one of {sorted(TAP_CONFIGS)}")
        problem = _load_problem(config_path=TAP_CONFIGS[fixture], hotspot_binary=None)
        return cls(problem, _load_legality(TAP_CONFIGS[fixture], problem))

    @property
    def fixture_id(self) -> str:
        return self.problem.fixture_id

    def design_from_centers(self, centers_mm, rotated=None) -> Design:
        """Build the controller Design for this fixture. rotated[i] turns die i by 90 degrees."""
        count = len(self.problem.widths_mm)
        if len(centers_mm) != count:
            raise TapLegalityError("TAP layout must provide one center per chiplet")
        rotated = (False,) * count if rotated is None else tuple(rotated)
        if len(rotated) != count or any(not isinstance(flag, bool) for flag in rotated):
            raise TapLegalityError("TAP layout must give one boolean rotation flag per chiplet")
        chiplets, positions = [], []
        for index, ((x, y), width, height, turned) in enumerate(
                zip(centers_mm, self.problem.widths_mm, self.problem.heights_mm, rotated)):
            if turned:
                width, height = height, width
            chiplets.append(Chiplet(f"tap-chiplet-{index}", width, height))
            positions.append((float(x) - width / 2, float(y) - height / 2))
        return Design(self.problem.interposer_size_mm, self.problem.interposer_size_mm, 0.0,
                      tuple(chiplets), tuple(positions))

    def rotated(self, candidate: Design) -> tuple[bool, ...]:
        """Which dies of a legal candidate sit turned 90 degrees from the configured orientation."""
        return tuple(not (_same_mm(chiplet.width_mm, width) and _same_mm(chiplet.height_mm, height))
                     for chiplet, width, height in zip(candidate.chiplets, self.problem.widths_mm,
                                                       self.problem.heights_mm))

    def centers_for(self, candidate: Design) -> tuple[tuple[float, float], ...]:
        if not isinstance(candidate, Design):
            raise TapLegalityError("TAP oracle requires a controller Design")
        try:
            candidate.check()
        except (TypeError, ValueError, OverflowError) as exc:
            raise TapLegalityError(f"invalid TAP candidate: {exc}") from exc
        catalog = self.legality.orientation_catalog_mm
        footprints = tuple((chiplet.width_mm, chiplet.height_mm) for chiplet in candidate.chiplets)
        if (len(footprints) != len(catalog) or
                any(not any(_same_mm(actual[0], width) and _same_mm(actual[1], height) for width, height in allowed)
                    for actual, allowed in zip(footprints, catalog))):
            raise TapLegalityError("TAP fixture chiplet catalog mismatch")
        size = self.problem.interposer_size_mm
        if not _same_mm(candidate.width_mm, size) or not _same_mm(candidate.height_mm, size):
            raise TapLegalityError("TAP fixture interposer size mismatch")
        violations = self.layout_violations(candidate)
        if violations:
            raise TapLegalityError(violations[0].message)
        return self._centers(candidate)

    @staticmethod
    def _centers(candidate: Design) -> tuple[tuple[float, float], ...]:
        # Centres come from each die's own footprint, so a turned die is placed as turned.
        return tuple((float(x + chiplet.width_mm / 2), float(y + chiplet.height_mm / 2))
                     for chiplet, (x, y) in zip(candidate.chiplets, candidate.positions))

    def layout_violations(self, candidate: Design) -> tuple[LayoutViolation, ...]:
        """Every placement-rule miss, in the order centers_for reports them: margins, lattice,
        halo overlaps, then minimum spacing. Reads each die's own (possibly turned) footprint."""
        size = self.problem.interposer_size_mm
        centers = self._centers(candidate)
        found = []
        margin = self.legality.margin_mm
        rectangles = []
        for index, (chiplet, (center_x, center_y), halo) in enumerate(
                zip(candidate.chiplets, centers, self.problem.bump_halos_mm)):
            rect = (center_x - chiplet.width_mm / 2 - halo,
                    center_y - chiplet.height_mm / 2 - halo,
                    center_x + chiplet.width_mm / 2 + halo,
                    center_y + chiplet.height_mm / 2 + halo)
            excess = max(margin - rect[0], margin - rect[1], rect[2] - (size - margin), rect[3] - (size - margin))
            if excess > 1e-9:
                found.append(LayoutViolation("margin", (index,), excess,
                             f"chiplet {index} violates the {margin:g} mm interposer margin with its microbump halo"))
            rectangles.append(rect)

        step = self.legality.center_lattice_mm
        if step is not None:
            for index, (center_x, center_y) in enumerate(centers):
                off = max(abs(center_x / step - round(center_x / step)), abs(center_y / step - round(center_y / step)))
                if off > 1e-9:
                    found.append(LayoutViolation("lattice", (index,), off * step,
                                 f"chiplet {index} center is off the {step:g} mm placement grid"))

        for index, rect in enumerate(rectangles):
            for other_index, other in enumerate(rectangles[:index]):
                if not (rect[2] <= other[0] or other[2] <= rect[0] or
                        rect[3] <= other[1] or other[3] <= rect[1]):
                    depth = min(min(rect[2], other[2]) - max(rect[0], other[0]),
                                min(rect[3], other[3]) - max(rect[1], other[1]))
                    found.append(LayoutViolation("halo_overlap", (other_index, index), depth,
                                 f"chiplets {other_index} and {index} overlap with their microbump halos"))

        min_gap = self.legality.min_die_gap_mm
        if min_gap > 0:
            # TAP-2.5D Eqn. (10): die bodies at least w_gap apart along some axis.
            bodies = [(rect[0] + halo, rect[1] + halo, rect[2] - halo, rect[3] - halo)
                      for rect, halo in zip(rectangles, self.problem.bump_halos_mm)]
            for index, body in enumerate(bodies):
                for other_index, other in enumerate(bodies[:index]):
                    spacing = max(other[0] - body[2], body[0] - other[2], other[1] - body[3], body[1] - other[3])
                    if spacing < min_gap - 1e-9:
                        apart = (f"are {spacing:.4f} mm apart" if spacing >= 0 else
                                 f"overlap by {-spacing:.4f} mm")
                        found.append(LayoutViolation("min_spacing", (other_index, index), min_gap - spacing,
                                     f"chiplets {other_index} and {index} {apart}, "
                                     f"under the {min_gap:g} mm minimum spacing"))
        return tuple(found)

    def wirelength_mm(self, centers: tuple[tuple[float, float], ...]) -> float:
        total_weight = sum(self.problem.connections[i][j]
                           for i in range(len(centers)) for j in range(i + 1, len(centers)))
        if total_weight <= 0 or not math.isfinite(total_weight):
            raise HotSpotOracleError("TAP benchmark has no positive connection weight")
        distance = sum(self.problem.connections[i][j] *
                       (abs(centers[i][0] - centers[j][0]) + abs(centers[i][1] - centers[j][1]))
                       for i in range(len(centers)) for j in range(i + 1, len(centers)))
        return distance / total_weight


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise HotSpotOracleError(f"worker returned invalid {label}")
    result = float(value)
    if not math.isfinite(result):
        raise HotSpotOracleError(f"worker returned non-finite {label}")
    return result


async def _terminate_process_group(process: asyncio.subprocess.Process, *, immediate=False) -> None:
    if os.name == "posix":
        if immediate:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        # The worker can exit on SIGTERM while HotSpot or another descendant
        # ignores it and keeps the inherited pipes open. Kill the isolated group
        # after the grace period even when the group leader has already exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            await process.wait()
    else:
        taskkill = None
        if process.returncode is None:
            try:
                taskkill = await asyncio.create_subprocess_exec(
                    "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                await asyncio.wait_for(taskkill.wait(), timeout=3.0)
            except (FileNotFoundError, OSError, asyncio.TimeoutError):
                if taskkill is not None and taskkill.returncode is None:
                    taskkill.kill()
                    await taskkill.wait()
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _uncancellable_cleanup(coroutine) -> None:
    """Finish process cleanup even when the caller is being cancelled."""
    task = asyncio.create_task(coroutine)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class _WarmWorker:
    """One persistent evaluator process and its private parent-owned workspace."""

    def __init__(self, process: asyncio.subprocess.Process, workspace: tempfile.TemporaryDirectory):
        self.process = process
        self.workspace = workspace
        self.broken = False
        self._stderr_tail = bytearray()
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    @classmethod
    async def start(cls) -> "_WarmWorker":
        workspace = tempfile.TemporaryDirectory(prefix="tfl-hotspot-worker-")
        process_options = ({"start_new_session": True} if os.name == "posix" else
                           {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP})
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(WORKER),
                cwd=str(TAP_ROOT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=MAX_WORKER_RESPONSE_BYTES,
                **process_options,
            )
        except BaseException:
            workspace.cleanup()
            raise
        return cls(process, workspace)

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def healthy(self) -> bool:
        return not self.broken and self.process.returncode is None

    async def _drain_stderr(self) -> None:
        assert self.process.stderr is not None
        while True:
            chunk = await self.process.stderr.read(4096)
            if not chunk:
                return
            self._stderr_tail.extend(chunk)
            if len(self._stderr_tail) > 8192:
                del self._stderr_tail[:-8192]

    async def _stderr_text(self) -> str:
        if self.process.returncode is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        return self._stderr_tail.decode("utf-8", errors="replace")[-2000:].strip()

    async def _exchange(self, payload: bytes) -> bytes:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(payload + b"\n")
        await self.process.stdin.drain()
        return await self.process.stdout.readline()

    async def evaluate(self, request: dict, *, worker_timeout_s: float) -> dict:
        self.immediate_kill = request.get('bounded_call', False)
        if not self.healthy:
            self.broken = True
            raise HotSpotOracleError("HotSpot worker is not available")
        message = dict(request)
        message["workspace_root"] = self.workspace.name
        try:
            encoded = json.dumps(message, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            self.broken = True
            raise HotSpotOracleError("HotSpot worker request is not valid JSON") from exc
        if len(encoded) > MAX_WORKER_REQUEST_BYTES:
            self.broken = True
            raise HotSpotOracleError("HotSpot worker request exceeds 64 KiB")

        try:
            line = await asyncio.wait_for(self._exchange(encoded), timeout=worker_timeout_s)
        except asyncio.TimeoutError as exc:
            self.broken = True
            raise HotSpotTimeoutError(f"HotSpot worker exceeded {worker_timeout_s:g} seconds") from exc
        except asyncio.CancelledError:
            self.broken = True
            raise
        except Exception as exc:
            self.broken = True
            detail = await self._stderr_text()
            raise HotSpotOracleError(detail or "HotSpot worker communication failed") from exc

        if not line:
            self.broken = True
            try:
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            detail = await self._stderr_text()
            raise HotSpotOracleError(detail or "HotSpot worker exited without a response")
        try:
            envelope = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.broken = True
            raise HotSpotOracleError("HotSpot worker returned invalid JSON") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
            self.broken = True
            raise HotSpotOracleError("HotSpot worker returned an invalid response envelope")
        if envelope["ok"] is not True:
            self.broken = True
            error = envelope.get("error")
            detail = error[:2000] if isinstance(error, str) else "HotSpot evaluation failed"
            if envelope.get("error_type") == "TimeoutError":
                raise HotSpotTimeoutError(detail or "HotSpot exceeded its solver timeout")
            raise HotSpotOracleError(detail)
        response = envelope.get("result")
        if not isinstance(response, dict):
            self.broken = True
            raise HotSpotOracleError("HotSpot worker returned an invalid result")
        return response

    async def close(self) -> None:
        self.broken = True
        started = time.perf_counter()
        try:
            await _terminate_process_group(self.process, immediate=getattr(self, 'immediate_kill', False))
        finally:
            self.kill_latency_s = time.perf_counter() - started
            self.workspace.cleanup()
            if not self._stderr_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=1.0)
                except asyncio.TimeoutError:
                    self._stderr_task.cancel()
                    await asyncio.gather(self._stderr_task, return_exceptions=True)


class _WarmWorkerPool:
    """Run-scoped pool: a worker is leased by one evaluation at a time."""

    def __init__(self, max_workers: int):
        self.loop = asyncio.get_running_loop()
        self._max_workers = max_workers
        self._capacity = asyncio.Semaphore(max_workers)
        self._available: asyncio.Queue[_WarmWorker] = asyncio.Queue()
        self._workers: set[_WarmWorker] = set()
        self._condition = asyncio.Condition()
        self._active = 0
        self._closing = False
        self._closed = False

    async def _retire(self, worker: _WarmWorker) -> None:
        self._workers.discard(worker)
        await _uncancellable_cleanup(worker.close())

    async def _spawn(self, *, immediate_kill=False) -> _WarmWorker:
        task = asyncio.create_task(_WarmWorker.start())
        try:
            worker = await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            worker = await task
            worker.immediate_kill = immediate_kill
            await _uncancellable_cleanup(worker.close())
            exc.kill_latency_s = worker.kill_latency_s
            raise
        worker.immediate_kill = immediate_kill
        self._workers.add(worker)
        return worker

    @asynccontextmanager
    async def lease(self, *, immediate_kill=False):
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("HotSpotOracle workers must be closed before using the oracle on another event loop")
        await self._capacity.acquire()
        active = False
        worker = None
        try:
            async with self._condition:
                if self._closing:
                    raise RuntimeError("HotSpotOracle worker pool is closed")
                self._active += 1
                active = True
            while worker is None:
                try:
                    candidate = self._available.get_nowait()
                except asyncio.QueueEmpty:
                    worker = await self._spawn(immediate_kill=immediate_kill)
                else:
                    if candidate.healthy:
                        worker = candidate
                    else:
                        await _uncancellable_cleanup(self._retire(candidate))
            try:
                yield worker
            except BaseException:
                retiring, worker = worker, None
                await _uncancellable_cleanup(self._retire(retiring))
                raise
            else:
                if worker.healthy and not self._closing:
                    self._available.put_nowait(worker)
                else:
                    retiring, worker = worker, None
                    await _uncancellable_cleanup(self._retire(retiring))
                if worker is not None:
                    worker = None
        finally:
            if worker is not None:
                retiring, worker = worker, None
                await _uncancellable_cleanup(self._retire(retiring))
            if active:
                async with self._condition:
                    self._active -= 1
                    self._condition.notify_all()
            self._capacity.release()

    async def close(self) -> None:
        if self._closed:
            return
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("HotSpotOracle worker pool must close on its owning event loop")
        async with self._condition:
            self._closing = True
            await self._condition.wait_for(lambda: self._active == 0)
        workers = tuple(self._workers)
        self._workers.clear()
        await asyncio.gather(*(_uncancellable_cleanup(worker.close()) for worker in workers))
        self._closed = True


class HotSpotOracle:
    """Async controller oracle backed by a run-scoped pool of isolated workers."""

    def __init__(self, grid_rows: int = 32, grid_cols: int = 32, *, fixture: str = TAP_CONFIG_DEFAULT_ID,
                 solver_timeout_s: float = 45.0, worker_timeout_s: float | None = None,
                 hotspot_binary: Path = HOTSPOT_BINARY, max_workers: int = DEFAULT_MAX_WORKERS,
                 retained_output_root: Path | None = None):
        if (isinstance(grid_rows, bool) or not isinstance(grid_rows, int) or not 1 <= grid_rows <= 128 or
                isinstance(grid_cols, bool) or not isinstance(grid_cols, int) or not 1 <= grid_cols <= 128):
            raise ValueError("grid rows and columns must be integers from 1 through 128")
        if (not isinstance(solver_timeout_s, numbers.Real) or isinstance(solver_timeout_s, bool) or
                not math.isfinite(solver_timeout_s) or solver_timeout_s <= 0):
            raise ValueError("solver_timeout_s must be positive")
        timeout = solver_timeout_s + 10.0 if worker_timeout_s is None else worker_timeout_s
        if (not isinstance(timeout, numbers.Real) or isinstance(timeout, bool) or
                not math.isfinite(timeout) or timeout <= solver_timeout_s):
            raise ValueError("worker_timeout_s must exceed solver_timeout_s")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if not isinstance(fixture, str) or fixture not in TAP_CONFIGS:
            raise ValueError(f"fixture must be one of {sorted(TAP_CONFIGS)}")

        self.fixture_id = fixture
        self.retained_output_root = None if retained_output_root is None else Path(retained_output_root).resolve()
        if self.retained_output_root is not None:
            self.retained_output_root.mkdir(parents=True, exist_ok=True)
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.solver_timeout_s = float(solver_timeout_s)
        self.worker_timeout_s = float(timeout)
        self.max_workers = max_workers
        self._worker_pool: _WarmWorkerPool | None = None
        self.hotspot_binary = Path(hotspot_binary).resolve()
        self.problem = _load_problem(config_path=TAP_CONFIGS[self.fixture_id], hotspot_binary=self.hotspot_binary)
        self.legality = _load_legality(TAP_CONFIGS[self.fixture_id], self.problem)
        self.solver_version = (
            f"HotSpot-7:{self.problem.hotspot_upstream_commit}"
            f":binary_sha256:{self.problem.hotspot_binary_sha256}"
            f":config_sha256:{self.problem.config_sha256}"
            f":grid:{self.grid_rows}x{self.grid_cols}"
        )
        self.problem_hash = _canonical_hash({
            "schema": "tfl-tap-hotspot-problem-v1",
            "fixture_id": self.problem.fixture_id,
            "tap_config_sha256": self.problem.config_sha256,
            "tap_hotspot_config_sha256": self.problem.hotspot_config_sha256,
            "tap_upstream_commit": self.problem.tap_upstream_commit,
            "hotspot_upstream_commit": self.problem.hotspot_upstream_commit,
            "hotspot_binary_sha256": self.problem.hotspot_binary_sha256,
            "generator_sha256": self.problem.generator_sha256,
            "grid": {"rows": self.grid_rows, "cols": self.grid_cols},
            "ambient_c": self.problem.ambient_c,
            "powers_w": self.problem.powers_w,
            "interposer_size_mm": self.problem.interposer_size_mm,
            "widths_mm": self.problem.widths_mm,
            "heights_mm": self.problem.heights_mm,
            "connections": self.problem.connections,
            "link_type": self.problem.link_type,
            "granularity_mm": self.problem.granularity_mm,
            "bump_halos_mm": self.problem.bump_halos_mm,
            "legality": asdict(self.legality),
            "model": "grid/detailed_3D/grid_map_mode=max",
            "wire_metric": "connectivity-weighted Manhattan center distance in mm; not routed CPLEX length",
        })

    def _get_worker_pool(self) -> _WarmWorkerPool:
        loop = asyncio.get_running_loop()
        if self._worker_pool is None:
            self._worker_pool = _WarmWorkerPool(self.max_workers)
        elif self._worker_pool.loop is not loop:
            raise RuntimeError("HotSpotOracle must be closed before using it on another event loop")
        return self._worker_pool

    async def aclose(self) -> None:
        """Terminate all run-scoped workers and their solver descendants."""
        pool = self._worker_pool
        if pool is None:
            return
        try:
            await _uncancellable_cleanup(pool.close())
        finally:
            if pool._closed:
                self._worker_pool = None

    @property
    def geometry(self) -> TapGeometry:
        """This oracle's fixture geometry and legality (built from the current problem)."""
        return TapGeometry(self.problem, self.legality)

    def design_from_centers(self, centers_mm: tuple[tuple[float, float], ...] | list[list[float]],
                            rotated=None) -> Design:
        """Build the controller Design expected for this fixed TAP benchmark."""
        return self.geometry.design_from_centers(centers_mm, rotated)

    def centers_for(self, candidate: Design) -> tuple[tuple[float, float], ...]:
        return self.geometry.centers_for(candidate)

    def _wirelength_mm(self, centers: tuple[tuple[float, float], ...]) -> float:
        return self.geometry.wirelength_mm(centers)

    async def __call__(self, candidate: Design, *, timeout_s: float | None = None) -> HotSpotThermalResult:
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError('call timeout must be positive and finite')
        self.last_kill_latency_s = None
        evaluation_started = time.perf_counter()
        # All legality checks happen before the worker is created or HotSpot is run.
        centers = self.centers_for(candidate)
        request = {
            "candidate_hash": candidate.hash,
            "problem_hash": self.problem_hash,
            "centers_mm": centers,
            # The worker turns these dies (TAP's own rotate) before it writes the floorplan.
            "rotated": list(self.geometry.rotated(candidate)),
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
            "solver_timeout_s": self.solver_timeout_s,
            "expected_binary_sha256": self.problem.hotspot_binary_sha256,
            "hotspot_binary": str(self.hotspot_binary),
            "expected_source_sha256": dict(self.problem.generator_sha256),
            "tap_parameters": {
                "interposer_size_mm": self.problem.interposer_size_mm,
                "widths_mm": self.problem.widths_mm,
                "heights_mm": self.problem.heights_mm,
                "powers_w": self.problem.powers_w,
                "connections": self.problem.connections,
                "link_type": self.problem.link_type,
                "granularity_mm": self.problem.granularity_mm,
                "bump_halos_mm": self.problem.bump_halos_mm,
                "ambient_c": self.problem.ambient_c,
            },
        }
        if self.retained_output_root is not None:
            request['retained_output_root'] = str(self.retained_output_root)
        if timeout_s is not None:
            request['solver_timeout_s'] = min(self.solver_timeout_s, timeout_s)
            request['bounded_call'] = True
        try:
            response = await _run_worker(
                request,
                worker_timeout_s=self.worker_timeout_s if timeout_s is None else min(self.worker_timeout_s, timeout_s),
                pool=self._get_worker_pool(),
                validator=lambda value: self._result_from_response(value, candidate, centers, evaluation_started),
            )
        except BaseException as exc:
            self.last_kill_latency_s = getattr(exc, 'kill_latency_s', None)
            if timeout_s is not None and isinstance(exc, (asyncio.CancelledError, HotSpotTimeoutError)):
                self._retain_interrupted_output(timeout_s)
            raise
        # Tests and adapters may replace _run_worker with a simple response stub;
        # the production pool validates inside the lease so malformed replies retire it.
        if isinstance(response, HotSpotThermalResult):
            return response
        return self._result_from_response(response, candidate, centers, evaluation_started)

    def _retain_interrupted_output(self, timeout_s):
        if self.retained_output_root is None:
            return
        for output in self.retained_output_root.glob('evaluation-*'):
            for name in ('stdout', 'stderr'):
                binary = output / f'{name}.bin'
                if binary.exists():
                    (output / f'{name}.txt').write_text(binary.read_bytes().decode('utf-8', errors='replace'))
            if not (output / 'EXIT.json').exists():
                (output / 'EXIT.json').write_text(json.dumps({
                    'status': 'parent_timeout', 'returncode': None, 'timeout_s': timeout_s,
                    'kill_latency_s': self.last_kill_latency_s}) + '\n')

    def _result_from_response(self, response: dict, candidate: Design,
                              centers: tuple[tuple[float, float], ...], evaluation_started: float
                              ) -> HotSpotThermalResult:
        if response.get("candidate_hash") != candidate.hash or response.get("problem_hash") != self.problem_hash:
            raise HotSpotOracleError("worker result is not bound to the requested design and problem")
        if response.get("binary_sha256") != self.problem.hotspot_binary_sha256:
            raise HotSpotOracleError("worker HotSpot binary differs from the problem contract")
        if response.get("grid_rows") != self.grid_rows or response.get("grid_cols") != self.grid_cols:
            raise HotSpotOracleError("worker returned a different grid resolution")

        rows = response.get("heatmap_c")
        if (not isinstance(rows, list) or len(rows) != self.grid_rows or
                any(not isinstance(row, list) or len(row) != self.grid_cols for row in rows)):
            raise HotSpotOracleError("worker returned an incomplete chip-layer heatmap")
        heatmap = tuple(tuple(_number(value, "heatmap temperature") for value in row) for row in rows)
        peak = _number(response.get("maximum_temperature_c"), "peak temperature")
        if not math.isclose(peak, max(max(row) for row in heatmap), rel_tol=0, abs_tol=1e-9):
            raise HotSpotOracleError("worker peak does not match its chip-layer heatmap")
        all_layers_peak = _number(response.get("all_layers_peak_c"), "all-layer peak temperature")
        if all_layers_peak < peak:
            raise HotSpotOracleError("worker all-layer peak is below its chip-layer peak")
        solver_seconds = _number(response.get("solver_seconds"), "solver runtime")
        generation_seconds = _number(response.get("input_generation_seconds"), "input generation runtime")
        if solver_seconds < 0 or generation_seconds < 0:
            raise HotSpotOracleError("worker returned a negative runtime")
        input_hashes = response.get("input_sha256")
        required_inputs = {
            "new_hotspot.config", "sampleL4_ChipLayer.flp", "sample.ptrace", "samplelayers.lcf",
            "sampleL0_Substrate.flp", "sampleL1_C4Layer.flp", "sampleL2_Interposer.flp",
            "sampleL3_UbumpLayer.flp", "sampleL5_TIM.flp",
        }
        if (not isinstance(input_hashes, dict) or not required_inputs.issubset(input_hashes) or
                any(not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                    for name, digest in input_hashes.items())):
            raise HotSpotOracleError("worker returned invalid generated-input hashes")

        return HotSpotThermalResult(
            candidate.hash,
            peak,
            self.solver_version,
            converged=True,
            cost_microdollars=0,
            evidence_kind=f"HotSpot 7 steady-state TAP {self.problem.fixture_id} grid; Manhattan wire proxy, not CPLEX routing",
            fixture_id=self.problem.fixture_id,
            config_sha256=self.problem.config_sha256,
            problem_hash=self.problem_hash,
            wirelength_mm=self._wirelength_mm(centers),
            wire_metric="connectivity-weighted Manhattan center distance (mm); not routed CPLEX length",
            heatmap_c=heatmap,
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
            ambient_c=self.problem.ambient_c,
            solver_seconds=solver_seconds,
            evaluation_seconds=time.perf_counter() - evaluation_started,
            input_generation_seconds=generation_seconds,
            input_sha256=tuple(sorted(input_hashes.items())),
            all_layers_peak_c=all_layers_peak,
        )


async def _run_worker(request: dict, *, worker_timeout_s: float,
                      pool: _WarmWorkerPool | None = None, validator=None):
    """Send one request to a leased warm worker; standalone calls own a short-lived pool."""
    owns_pool = pool is None
    pool = pool or _WarmWorkerPool(max_workers=1)
    worker = None
    try:
        async with pool.lease(immediate_kill=request.get('bounded_call', False)) as worker:
            response = await worker.evaluate(request, worker_timeout_s=worker_timeout_s)
            return validator(response) if validator is not None else response
    except BaseException as exc:
        exc.kill_latency_s = getattr(worker, 'kill_latency_s', getattr(exc, 'kill_latency_s', None))
        raise
    finally:
        if owns_pool:
            await _uncancellable_cleanup(pool.close())
