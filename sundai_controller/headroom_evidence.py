"""Per-call retained evidence helpers. No solver execution on import."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import re
import time

ROOT = Path(__file__).resolve().parents[1]


def self_cpu():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def stamp():
    return self_cpu(), time.perf_counter()


def elapsed(start):
    return {'cpu_seconds': max(0.0, self_cpu() - start[0]),
            'wall_seconds': max(0.0, time.perf_counter() - start[1])}


def execution_identity(oracle):
    """Bind the actual binary/config/source bytes; missing image ID is explicit."""
    from sundai_hotspot.tap_oracle import _worker_environment
    files = ['sundai_controller/headroom.py', 'sundai_controller/headroom_evidence.py',
             'sundai_controller/evidence_profile.py', 'sundai_controller/headroom_supervisor.py',
             'sundai_controller/process_budget.py', 'sundai_controller/controller.py',
             'sundai_controller/experiment.py', 'sundai_hotspot/tap_oracle.py',
             'sundai_hotspot/tap_oracle_worker.py', 'requirements.txt']
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    sources.update(dict(oracle.problem.generator_sha256))
    for path in (ROOT / 'sundai_hotspot').iterdir():
        if path.suffix in ('.c', '.h') or path.name in ('Makefile', 'UPSTREAM_COMMIT'):
            sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    image = {'status': 'unavailable', 'reason': 'No resolved runtime image digest supplied by the host',
             'dockerfile_sha256': hashlib.sha256((ROOT / 'Dockerfile').read_bytes()).hexdigest()}
    digest = os.environ.get('SENTILAB_IMAGE_DIGEST')
    if digest is not None:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError('SENTILAB_IMAGE_DIGEST must be a resolved sha256 image digest')
        image = {'status': 'host_declared', 'digest': digest,
                 'dockerfile_sha256': image['dockerfile_sha256']}
    build = ROOT / 'build-info.json'
    if build.exists():
        image['build_info_sha256'] = hashlib.sha256(build.read_bytes()).hexdigest()
        image['base_image_digest'] = json.loads(build.read_bytes()).get('base_image_digest')
        # A base-image pin is not the final runtime-image identity.
    return {'fixture': oracle.fixture_id, 'grid': oracle.grid_rows,
            'binary_sha256': oracle.problem.hotspot_binary_sha256,
            'config_sha256': oracle.problem.config_sha256, 'problem_hash': oracle.problem_hash,
            'hotspot_upstream_commit': oracle.problem.hotspot_upstream_commit,
            'tap_upstream_commit': oracle.problem.tap_upstream_commit,
            'source_sha256': sources, 'image_identity': image,
            'runtime': {'python': platform.python_version(), 'machine': platform.machine(),
                        'kernel': platform.release(), 'environment': _worker_environment()}}


def native_phases(raw_dir):
    """Read only durable checkpoints; absence means unknown, never zero measured CPU."""
    if raw_dir is None:
        return {}
    files = list(Path(raw_dir).glob('evaluation-*/PHASES.json'))
    if len(files) != 1:
        return {}
    try:
        data = json.loads(files[0].read_bytes())
    except (OSError, ValueError):
        return {}  # Unknown phase measurements cannot produce an admissible profile.
    return data.get('phase_timings', data.get('phases', data))


def record_call(path, history, *, archive_started, call_started_cpu, cpu_clock):
    """Archive once, measure that work, then persist the final measured receipt.

    Final receipt serialization is charged by the run ledger/supervisor. It is
    intentionally covered by the declared reserve, not a recursive self-timing.
    """
    from sundai_controller.headroom import _write_json
    phases = history.setdefault('phase_timings', {})
    _write_json(path, history)
    archive = elapsed(archive_started)
    native_archive = phases.get('archive', {'cpu_seconds': 0, 'wall_seconds': 0})
    phases['archive'] = {key: archive[key] + native_archive[key] for key in archive}
    total = max(0.0, cpu_clock() - call_started_cpu)
    known = sum(value['cpu_seconds'] for key, value in phases.items() if key != 'overhead')
    phases['overhead'] = {'cpu_seconds': max(0.0, total - known), 'wall_seconds': 0.0}
    history['metered_cpu_seconds'] = total
    history['phase_accounting'] = 'Non-overlapping CPU; overhead is reconciled residual. Final receipt write charged by ledger/supervisor and forecast reserve.'
    history['profile_complete'] = all(key in phases for key in
                                    ('generate', 'solve', 'worker_startup', 'teardown_reap', 'archive'))
    _write_json(path, history)


def available_cpu(prereg, state):
    """Same historical ceilings as SolveBudget; existing charges only subtract."""
    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('allocation CPU limits and charges must be finite and nonnegative')
        return value
    number(state.get('cpu_seconds', 0))
    number(state.get('non_headroom', {}).get('cpu_seconds', 0))
    for entry in state.get('fixtures', {}).values():
        number(entry.get('cpu_seconds', 0))
    for key in ('headroom_cpu_minutes', 'aggregate_cpu_minutes'):
        number(prereg.get('allocation', {}).get(key, 0))
    number(prereg.get('allocation', {}).get('per_fixture', {}).get('cpu_minutes', 0))
    if prereg['schema'] == 'slab-039-prereg-v4':
        from sundai_controller.headroom_supervisor import remaining_cpu
        return remaining_cpu(state, prereg)
    if state.get('allocation_halted') or state.get('active') or state.get('outer_active'):
        raise ValueError('allocation halted or unreconciled reservation')
    allocation = prereg.get('allocation', {})
    fixture = allocation.get('per_fixture', {})
    spent = state.get('fixtures', {}).get(prereg['fixture'], {}).get('cpu_seconds', 0)
    return min(min(48, allocation.get('headroom_cpu_minutes', 48)) * 60 - state.get('cpu_seconds', 0),
               min(24, fixture.get('cpu_minutes', 24)) * 60 - spent)


def finalize_call(path, history, *, ledger_started, call_started_cpu, cpu_clock):
    """Include the durable charge/ledger write in the measured archive cost."""
    from sundai_controller.headroom import _write_json
    duration = elapsed(ledger_started)
    phases = history['phase_timings']
    for key, value in duration.items():
        phases['archive'][key] += value
    total = max(0.0, cpu_clock() - call_started_cpu)
    known = sum(value['cpu_seconds'] for key, value in phases.items() if key != 'overhead')
    phases['overhead']['cpu_seconds'] = max(0.0, total - known)
    history['metered_cpu_seconds'] = total
    _write_json(path, history)


def check_declared_calls(prereg, state, count):
    """Reject a schedule that cannot fit the remaining durable call allocation."""
    allocation = prereg.get('allocation', {})
    per_fixture = allocation.get('per_fixture', {})
    def integer(value):
        if type(value) is not int or value < 0:
            raise ValueError('allocation call limits and charges must be nonnegative integers')
        return value
    total = integer(state.get('total_calls', 0))
    fixture = integer(state.get('fixtures', {}).get(prereg['fixture'], {}).get('calls', 0))
    remaining = min(min(9700, integer(allocation.get('headroom_solve_limit', 9700))) - total,
                    min(4768, integer(per_fixture.get('total_solves', 4768))) - fixture)
    if prereg['schema'] == 'slab-039-prereg-v4':
        other = max(300, integer(state.get('non_headroom', {}).get('calls', 0)))
        remaining = min(remaining, min(10000, integer(allocation.get('aggregate_solve_limit', 10000))) - total - other)
    if count > remaining:
        raise ValueError(f'call cap shortfall: {count - remaining} calls; {count} declared, {remaining} available')
