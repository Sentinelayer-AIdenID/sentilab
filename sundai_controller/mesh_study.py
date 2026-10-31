"""Freeze a geometry-only layout sample, then measure HotSpot mesh uncertainty.

Freeze and commit layouts.json plus layouts.sha256 before evaluating temperatures.
J is the chip-layer grid peak in Celsius, not the all-layer or block peak.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import time

from sundai_hotspot.tap_oracle import HotSpotOracle

CATEGORIES = ('clustered', 'spread', 'random')
FIXED_TOLERANCE_C = 0.01
MAX_RECEIPT_BYTES = 1024 * 1024
EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/mesh'


def make_oracle(fixture: str, grid: int) -> HotSpotOracle:
    if fixture not in ('ascend910', 'micro150'):
        raise ValueError(f'unsupported fixture: {fixture}')
    return HotSpotOracle(grid, grid, fixture=fixture, max_workers=1)


def fixture_contract(oracle):
    # Geometry freeze is portable across builds; fixture name and evaluator are checked separately.
    problem = asdict(oracle.problem)
    return {key: value for key, value in problem.items()
            if key not in ('fixture_id', 'hotspot_binary_sha256', 'generator_sha256')}


def evaluator_identity(problem):
    return json.loads(_json_bytes({key: problem[key] for key in
                                  ('hotspot_binary_sha256', 'generator_sha256')}))


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _distance(centers):
    pairs = list(itertools.combinations(centers, 2))
    return sum(math.dist(a, b) for a, b in pairs) / len(pairs)


def make_layout_set(fixture: str, seed: int, n: int) -> dict:
    """Select extremes of geometric dispersion and a random remainder, never J.

    Generate max(256,16*n) unique legal packings using seeded randomized greedy
    placement on the fixture grid. Select n//3 smallest/largest mean pairwise
    center distances; distribute the remainder in category order. Random draws
    come from the remaining pool. Cluster/spread are relative to this fixed pool.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 3:
        raise ValueError('n must be an integer >= 3')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    oracle = make_oracle(fixture, 16)
    p = oracle.problem
    rng = random.Random(seed)
    domains = []
    for w, h, halo in zip(p.widths_mm, p.heights_mm, p.bump_halos_mm):
        ranges = []
        for size in (w, h):
            lo = math.ceil((size / 2 + halo + 0.5) / p.granularity_mm)
            hi = math.floor((p.interposer_size_mm - size / 2 - halo - 0.5) / p.granularity_mm)
            ranges.append([i * p.granularity_mm for i in range(lo, hi + 1)])
        domains.append(list(itertools.product(*ranges)))
    order = sorted(range(len(domains)), key=lambda i: -p.widths_mm[i] * p.heights_mm[i])
    pool = {}
    pool_size = max(256, 16 * n)
    for _ in range(pool_size * 100):
        centers = [None] * len(domains)
        rectangles = []
        for i in order:
            choices = domains[i].copy()
            rng.shuffle(choices)
            for x, y in choices:
                hw, hh = p.widths_mm[i] / 2 + p.bump_halos_mm[i], p.heights_mm[i] / 2 + p.bump_halos_mm[i]
                rect = (x - hw, y - hh, x + hw, y + hh)
                if all(rect[2] <= r[0] or r[2] <= rect[0] or rect[3] <= r[1] or r[3] <= rect[1]
                       for r in rectangles):
                    centers[i] = (x, y)
                    rectangles.append(rect)
                    break
            if centers[i] is None:
                break
        if None in centers:
            continue
        design = oracle.design_from_centers(centers)
        oracle.centers_for(design)
        pool[design.hash] = {'centers_mm': centers, 'design_hash': design.hash,
                             'mean_pair_distance_mm': _distance(centers)}
        if len(pool) == pool_size:
            break
    if len(pool) != pool_size:
        raise RuntimeError('could not generate the predeclared legal geometry pool')
    ordered = sorted(pool.values(), key=lambda row: (row['mean_pair_distance_mm'], row['design_hash']))
    counts = [n // 3 + (i < n % 3) for i in range(3)]
    groups = (ordered[:counts[0]], ordered[-counts[1]:],
              rng.sample(ordered[counts[0]:-counts[1]], counts[2]))
    layouts = [{**row, 'id': f'{category}-{i + 1:02d}', 'category': category}
               for category, group in zip(CATEGORIES, groups) for i, row in enumerate(group)]
    return json.loads(_json_bytes({
        'schema': 'slab-mesh-layouts-v1', 'fixture': fixture, 'seed': seed, 'n': n,
        'generator': 'seeded-greedy-grid-pool-v1', 'pool_size': pool_size,
        'selection': 'geometry-only mean Euclidean pairwise center distance extremes; random remainder',
        'fixed_tolerance_c': FIXED_TOLERANCE_C, 'fixture_contract': fixture_contract(oracle),
        'layouts': layouts,
    }))


def freeze_layouts(path: Path, frozen: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _json_bytes(frozen)
    # Exclusive creation prevents replacing the sample after looking at results.
    with path.open('xb') as stream:
        stream.write(data)
    with path.with_suffix('.sha256').open('x', encoding='utf-8') as stream:
        stream.write(hashlib.sha256(data).hexdigest() + '\n')


def load_layouts(path: Path):
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if path.with_suffix('.sha256').read_text(encoding='utf-8').strip() != sha:
        raise ValueError('layouts sha256 mismatch')
    frozen = json.loads(data)
    if frozen['schema'] != 'slab-mesh-layouts-v1' or len(frozen['layouts']) != frozen['n']:
        raise ValueError('invalid frozen layout schema or count')
    ids = [row['id'] for row in frozen['layouts']]
    hashes = [row['design_hash'] for row in frozen['layouts']]
    if len(set(ids)) != len(ids) or len(set(hashes)) != len(hashes):
        raise ValueError('duplicate frozen layout identity')
    return frozen, sha


def _values(coarse, reference):
    if len(coarse) != len(reference) or not coarse:
        raise ValueError('nonempty equal-length measurements required')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in [*coarse, *reference]):
        raise ValueError('finite numeric measurements required')


def mesh_error(coarse, reference) -> float:
    _values(coarse, reference)
    return max(abs(a - b) for a, b in zip(coarse, reference))


def rank_agreement(coarse, reference, tolerance_c: float) -> dict:
    """Compare exact coarse signs only where the reference gap exceeds tolerance.

    Equality at the tolerance is excluded (1e-12 C roundoff guard). A coarse tie on an eligible pair is
    a violation. Zero eligible pairs yields no agreement fraction or pass verdict.
    """
    _values(coarse, reference)
    if (isinstance(tolerance_c, bool) or not isinstance(tolerance_c, (int, float))
            or not math.isfinite(tolerance_c) or tolerance_c < 0):
        raise ValueError('tolerance must be finite and nonnegative')
    eligible = 0
    coarse_ties = 0
    violations = []
    total = len(reference) * (len(reference) - 1) // 2
    for i, j in itertools.combinations(range(len(reference)), 2):
        fine_gap = reference[i] - reference[j]
        if (abs(fine_gap) <= tolerance_c
                or math.isclose(abs(fine_gap), tolerance_c, rel_tol=0, abs_tol=1e-12)):
            continue
        eligible += 1
        coarse_gap = coarse[i] - coarse[j]
        if coarse_gap == 0 or (coarse_gap > 0) != (fine_gap > 0):
            violations.append([i, j])
            coarse_ties += coarse_gap == 0
    return {'tolerance_c': tolerance_c, 'total_pairs': total, 'eligible_pairs': eligible,
            'excluded_pairs': total - eligible, 'violations': len(violations),
            'inversions': len(violations) - coarse_ties, 'coarse_ties': coarse_ties,
            'violation_pairs': violations, 'passes': (not violations) if eligible else None,
            'max_misordered_reference_gap_c': max(
                (abs(reference[i] - reference[j]) for i, j in violations), default=0.0),
            'agreement_fraction': (eligible - len(violations)) / eligible if eligible else None}


def summarize(rows, grids, fixed_tolerance_c):
    reference_grid = max(grids)
    reference = [r['J_c'][str(reference_grid)] for r in rows]
    comparisons = {}
    for grid in grids:
        if grid == reference_grid:
            continue
        coarse = [r['J_c'][str(grid)] for r in rows]
        error = mesh_error(coarse, reference)
        comparisons[str(grid)] = {'max_abs_error_c': error,
                                 'max_misordered_reference_gap_c': rank_agreement(
                                     coarse, reference, 0)['max_misordered_reference_gap_c'],
                                 'rank_2e': rank_agreement(coarse, reference, 2 * error),
                                 'rank_fixed': rank_agreement(coarse, reference, fixed_tolerance_c)}
    return {'reference_grid': reference_grid,
            'e_c': comparisons.get('32', {}).get('max_abs_error_c') if reference_grid == 64 else None,
            'e16_c': comparisons.get('16', {}).get('max_abs_error_c') if reference_grid == 64 else None,
            'comparisons': comparisons}


def check_result(result: dict, evidence_dir: Path | None = None) -> list[str]:
    """Recompute summaries and test the published tolerance without inflating it.

    An edited J cannot silently increase the frozen 2e bound and hide an inversion.
    This checks internal consistency, not authenticity; rerun HotSpot for that.
    With evidence_dir, also verify the journal and its aggregate references.
    """
    errors = []
    try:
        rows, grids = result['layouts'], result['grids']
        if len(rows) < 2 or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('need at least two unique layout ids')
        if len(set(grids)) != len(grids) or len(grids) < 2 or any(g not in (16, 32, 64) for g in grids):
            raise ValueError('need distinct grids chosen from 16, 32, 64')
        if any(set(r['J_c']) != {str(g) for g in grids} for r in rows):
            raise ValueError('measurement grids mismatch')
        provenance = result['provenance']
        if set(provenance) != {str(g) for g in grids}:
            raise ValueError('evaluator identity missing for a grid')
        pinned = result['evaluator_identity']
        if any(evaluator_identity(provenance[str(g)]['problem']) != pinned for g in grids):
            errors.append('evaluator identity changed across grids')
        summary = summarize(rows, grids, result['fixed_tolerance_c'])
        if summary != result['summary']:
            errors.append('stored summary differs from measured values')
        if evidence_dir is not None and 'rows_evidence' in result:
            check_receipts(result, evidence_dir)
        reference = [r['J_c'][str(max(grids))] for r in rows]
        for grid, comparison in result['summary']['comparisons'].items():
            coarse = [r['J_c'][grid] for r in rows]
            rank = rank_agreement(coarse, reference, comparison['rank_2e']['tolerance_c'])
            if rank['violations']:
                errors.append(f'grid {grid}: {rank["violations"]} inversion/tie violations at published 2e tolerance')
    except (KeyError, TypeError, ValueError, OSError) as exc:
        errors.append(f'invalid result: {exc}')
    return errors


def check_receipts(result, evidence_dir):
    evidence = result['rows_evidence']
    if evidence['path'] != 'rows.jsonl':
        raise ValueError('invalid receipt journal path')
    path = Path(evidence_dir) / 'rows.jsonl'
    if not path.resolve().is_relative_to(Path(evidence_dir).resolve()):
        raise ValueError('receipt journal escapes evidence directory')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != evidence['sha256']:
        raise ValueError('receipt journal sha256 mismatch')
    records = [json.loads(line) for line in data.splitlines()]
    count = result['evaluation_count']
    if (not records or records[0].get('kind') != 'run'
            or records[-1].get('kind') != 'completion'
            or records[-1].get('status') != 'complete'
            or records[-1].get('evaluation_count') != count):
        raise ValueError('receipt journal is incomplete')
    header = records[0]
    expected = {(row['id'], grid) for row in result['layouts'] for grid in result['grids']}
    if (any(header[field] != result[field] for field in ('fixture', 'grids', 'layouts_sha256'))
            or header['layout_ids'] != [row['id'] for row in result['layouts']]
            or header['expected_evaluations'] != len(expected)):
        raise ValueError('receipt run header differs from result')
    evaluations = [r for r in records if r['kind'] == 'evaluation']
    if (count != len(expected) or len(evaluations) != count or evidence['evaluation_count'] != count
            or [r['sequence'] for r in evaluations] != list(range(1, count + 1))):
        raise ValueError('receipt journal count or sequence mismatch')
    if {(entry['layout_id'], entry['grid']) for entry in evaluations} != expected:
        raise ValueError('receipt coverage must include each layout and grid exactly once')
    for row in result['layouts']:
        if set(row['receipt_sequence']) != {str(grid) for grid in result['grids']}:
            raise ValueError('receipt sequence grids mismatch')
        for grid in result['grids']:
            sequence = row['receipt_sequence'][str(grid)]
            if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= count:
                raise ValueError('invalid receipt sequence')
            entry = evaluations[sequence - 1]
            receipt = entry['parsed_receipt']
            heatmap = receipt['heatmap_c']
            if (not isinstance(heatmap, list) or len(heatmap) != grid
                    or any(not isinstance(line, list) or len(line) != grid for line in heatmap)):
                raise ValueError('receipt heatmap dimensions differ from grid')
            peak = receipt['maximum_temperature_c']
            if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) for line in heatmap for value in line)
                    or isinstance(peak, bool) or not isinstance(peak, (int, float))
                    or not math.isfinite(peak)):
                raise ValueError('receipt heatmap and peak must be finite numbers')
            if not math.isclose(peak, max(max(line) for line in heatmap), rel_tol=0, abs_tol=1e-9):
                raise ValueError('receipt heatmap peak differs from declared peak')
            if (entry['layout_id'] != row['id'] or entry['grid'] != grid
                    or entry['evaluator_identity'] != result['evaluator_identity']
                    or receipt['candidate_hash'] != row['design_hash']
                    or receipt['problem_hash'] != result['provenance'][str(grid)]['problem_hash']
                    or receipt['grid_rows'] != grid or receipt['grid_cols'] != grid
                    or not receipt['input_sha256']
                    or hashlib.sha256(_json_bytes(receipt['heatmap_c'])).hexdigest() != entry['heatmap_sha256']):
                raise ValueError('receipt identity or heatmap hash mismatch')
            for field, aggregate in [('maximum_temperature_c', 'J_c'),
                                     ('all_layers_peak_c', 'all_layers_peak_c'),
                                     ('evaluation_seconds', 'seconds'), ('solver_seconds', 'solver_seconds'),
                                     ('candidate_hash', 'candidate_hash')]:
                if receipt[field] != row[aggregate][str(grid)]:
                    raise ValueError('receipt differs from aggregate result')


def cpu_usage():
    """POSIX process CPU plus reaped workers and their reaped solver children.

    Read the final sample only after aclose() has waited for every worker.
    Run this harness in a dedicated process: unrelated child work is included.
    """
    import resource

    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return (own.ru_utime + own.ru_stime, children.ru_utime + children.ru_stime)


def run_accounting(start_cpu, solver_executions):
    end_cpu = cpu_usage()
    own, children = (end - start for start, end in zip(start_cpu, end_cpu))
    return {'solver_executions': solver_executions, 'warmup_solver_executions': 0,
            'process_cpu_seconds': own, 'children_cpu_seconds': children,
            'cpu_seconds': own + children, 'cpu_minutes': (own + children) / 60,
            'method': 'POSIX getrusage SELF + CHILDREN delta after worker shutdown',
            'scope': 'this evaluation run, including worker startup and shutdown; no warm-up runs'}


def append_receipt(stream, value):
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError('evaluation receipt exceeds 1 MiB')
    stream.write(data)
    stream.flush()
    os.fsync(stream.fileno())


async def evaluate_layouts(frozen, grids=(16, 32, 64), layout_ids=None, *, evidence_dir: Path,
                           layouts_sha256: str | None = None):
    if len(set(grids)) != len(grids) or len(grids) < 2 or any(g not in (16, 32, 64) for g in grids):
        raise ValueError('choose at least two distinct grids from 16, 32, 64')
    selected = frozen['layouts']
    if layout_ids is not None:
        if not set(layout_ids) <= {r['id'] for r in selected}:
            raise ValueError('unknown layout id')
        selected = [r for r in selected if r['id'] in layout_ids]
    if len(selected) < 2:
        raise ValueError('select at least two layouts')
    # File-backed runs supply the hash of the exact frozen bytes they loaded.
    if layouts_sha256 is None:
        layouts_sha256 = hashlib.sha256(_json_bytes(frozen)).hexdigest()
    rows = [{**r, 'J_c': {}, 'all_layers_peak_c': {}, 'seconds': {},
             'solver_seconds': {}, 'candidate_hash': {}, 'receipt_sequence': {}} for r in selected]
    started = time.perf_counter()
    start_cpu = cpu_usage()
    solver_executions = 0
    provenance = {}
    pinned = None
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    journal = evidence_dir / 'rows.jsonl'
    # Exclusive creation reserves the run before evaluating. Never append a rerun
    # to historical evidence. A missing completion record means incomplete.
    with journal.open('xb') as stream:
        append_receipt(stream, {'kind': 'run', 'status': 'incomplete',
                               'fixture': frozen['fixture'], 'grids': list(grids),
                               'layouts_sha256': layouts_sha256,
                               'layout_ids': [r['id'] for r in rows],
                               'expected_evaluations': len(rows) * len(grids),
                               'raw_artifacts_retained': False})
        for grid in grids:
            oracle = make_oracle(frozen['fixture'], grid)
            try:
                if getattr(oracle.problem, 'fixture_id', frozen['fixture']) != frozen['fixture']:
                    raise ValueError('oracle fixture id does not match frozen fixture')
                if json.loads(_json_bytes(fixture_contract(oracle))) != frozen['fixture_contract']:
                    raise ValueError('frozen fixture contract changed')
                identity = evaluator_identity(asdict(oracle.problem))
                if pinned is None:
                    pinned = identity
                elif identity != pinned:
                    raise ValueError('evaluator identity changed before next grid')
                provenance[str(grid)] = {'problem_hash': oracle.problem_hash,
                                         'solver_version': oracle.solver_version,
                                         'problem': asdict(oracle.problem)}
                append_receipt(stream, {'kind': 'grid', 'grid': grid,
                                        'evaluator_identity': pinned, 'provenance': provenance[str(grid)]})
                for row in rows:
                    design = oracle.design_from_centers(row['centers_mm'])
                    oracle.centers_for(design)
                    if design.hash != row['design_hash']:
                        raise ValueError('frozen design hash mismatch')
                    result = await oracle(design)
                    solver_executions += 1
                    # Persist the complete parsed return before the next await.
                    # A failed later call or cancellation cannot discard this row.
                    append_receipt(stream, {
                        'kind': 'evaluation', 'sequence': solver_executions,
                        'layout_id': row['id'], 'grid': grid,
                        'evaluator_identity': pinned,
                        'heatmap_sha256': hashlib.sha256(_json_bytes(result.heatmap_c)).hexdigest(),
                        'parsed_receipt': asdict(result),
                    })
                    row['J_c'][str(grid)] = result.maximum_temperature_c
                    row['all_layers_peak_c'][str(grid)] = result.all_layers_peak_c
                    row['seconds'][str(grid)] = result.evaluation_seconds
                    row['solver_seconds'][str(grid)] = result.solver_seconds
                    row['candidate_hash'][str(grid)] = result.candidate_hash
                    row['receipt_sequence'][str(grid)] = solver_executions
            finally:
                await oracle.aclose()
        result = {'schema': 'slab-mesh-result-v1', 'fixture': frozen['fixture'],
                  'layouts_sha256': layouts_sha256,
                  'grids': list(grids), 'fixed_tolerance_c': frozen['fixed_tolerance_c'],
                  'objective': 'chip-layer grid peak in Celsius', 'layouts': rows,
                  'evaluation_count': solver_executions, 'seconds': time.perf_counter() - started,
                  'run_accounting': run_accounting(start_cpu, solver_executions),
                  'evaluator_identity': pinned, 'provenance': provenance,
                  'summary': summarize(rows, grids, frozen['fixed_tolerance_c']),
                  'evidence_status': {'parsed_receipts_retained': True,
                                      'raw_artifacts_retained': False, 'D02_complete': False,
                                      'limitation': 'Raw solver archival awaits the oracle artifact seam.'}}
        errors = check_result(result)
        if errors:
            raise ValueError('; '.join(errors))
        append_receipt(stream, {'kind': 'completion', 'status': 'complete',
                               'evaluation_count': solver_executions,
                               'run_accounting': result['run_accounting']})
    result['rows_evidence'] = {'path': journal.name, 'sha256': hashlib.sha256(journal.read_bytes()).hexdigest(),
                               'evaluation_count': solver_executions}
    return result


def report(result):
    summary = result['summary']
    lines = [f'# Mesh study: {result["fixture"]}', '',
             f'{len(result["layouts"])} frozen layouts; {result["evaluation_count"]} evaluations; '
             f'{result["seconds"]:.3f} seconds. J is the chip-layer grid peak (Celsius).', '',
             f'Layouts SHA-256: `{result["layouts_sha256"]}`.',
             f'Execution commit: `{result["execution_commit"]}`.', '',
             f'Reference: {summary["reference_grid"]}x{summary["reference_grid"]}. '
             f'e = max |J32-J64| = {summary["e_c"]} C; e16 = max |J16-J64| = {summary["e16_c"]} C.', '',
             '## Rank rule', '',
             '32 passes if violations = 0 and at least one pair is eligible: '
             'for each pair with |J64(a)-J64(b)| > 2e, '
             'the signs of J32(a)-J32(b) and J64(a)-J64(b) must agree. '
             '16 uses its own 2e16. Equality at the tolerance is excluded (1e-12 C roundoff guard); a coarse tie is a violation.', '',
             'Because e is the maximum error on this same sample, the triangle inequality guarantees '
             'no inversions beyond 2e. This pass is an internal consistency check, not independent '
             'evidence that all ranks agree. Zero eligible pairs is inconclusive (null pass verdict). '
             'The predeclared fixed 0.01 C tolerance provides an additional ranking diagnostic.', '',
             '| Grid | Max error C | 2e tolerance C | Eligible / total | Violations | Pass | '
             'Fixed 0.01 C eligible | Fixed inversions | Fixed coarse ties |',
             '| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |']
    for grid, comparison in summary['comparisons'].items():
        rank, fixed = comparison['rank_2e'], comparison['rank_fixed']
        lines.append(f'| {grid} | {comparison["max_abs_error_c"]:.6f} | {rank["tolerance_c"]:.6f} | '
                     f'{rank["eligible_pairs"]} / {rank["total_pairs"]} | {rank["violations"]} | '
                     f'{rank["passes"]} | {fixed["eligible_pairs"]} | '
                     f'{fixed["inversions"]} | {fixed["coarse_ties"]} |')
    lines += ['', '## Observed ranking resolution', '']
    for grid, comparison in summary['comparisons'].items():
        gap = comparison['max_misordered_reference_gap_c']
        lines.append(f'Grid {grid}: largest reference-grid gap reversed or left tied is {gap:.6f} C.')
    lines += ['', 'This statistic compares all unequal reference pairs (zero tie tolerance, '
              'with the same roundoff guard). It measures gaps on the reference grid, not '
              'coarse-grid differences, and is an observation on these layouts, not a '
              'guaranteed threshold for unseen layouts.', '']
    lines += ['', '## Measured peaks (C)', '',
              '| Layout | ' + ' | '.join(f'J{grid}' for grid in result['grids']) + ' |',
              '| --- | ' + ' | '.join('---:' for _ in result['grids']) + ' |']
    for row in result['layouts']:
        lines.append('| ' + row['id'] + ' | ' + ' | '.join(
            f'{row["J_c"][str(grid)]:.2f}' for grid in result['grids']) + ' |')
    accounting = result.get('run_accounting', {})
    cpu_minutes = accounting.get('cpu_minutes')
    cpu_label = 'not measured; budget compliance is unverified' if cpu_minutes is None else f'{cpu_minutes:.6f}'
    lines += ['', '## Resource accounting', '',
              f'Solver executions in this run: {accounting.get("solver_executions", "not recorded")}. '
              f'CPU-minutes (process plus reaped children): {cpu_label}.', '',
              'Per-run accounting is not a shared-budget clearance. See VALIDATION.md in this '
              'evidence directory for the reservation, validation use and remaining allowance; '
              'historical accounting limitations are recorded in ../VALIDATION.md.', '']
    evidence = result.get('evidence_status', {})
    lines += ['', '## Retained evidence', '',
              'Raw HotSpot inputs and outputs are not retained; D02 is incomplete.',
              ('Full parsed receipts, input hashes, heatmaps and heatmap hashes are in rows.jsonl; '
               'RESULT.json binds the journal hash and per-row sequence numbers.'
               if evidence.get('parsed_receipts_retained') else
               'The historical run also discarded per-evaluation input hashes and heatmaps. '
               'These cannot be reconstructed from the retained peak values.'), '']
    lines += ['', '## Scope', '',
              'e is an empirical discrepancy against 64 on this fixed layout set, not an error bound '
              'against the continuum or unseen layouts. Later R4/u_num and SLAB-039 margins can use e '
              'with that scope; a two-layout difference needs a margin greater than 2e. '
              'The fixed 0.01 C tolerance is a sensitivity diagnostic, not measured numerical '
              'uncertainty or a practical minimum effect. '
              'The 16-grid error and fixed-tolerance inversions show the limits of cheap screening. '
              'No benchmark method-gap or continuum-convergence claim is made here.', '',
              'All J values, per-evaluation timings, design hashes, problem/config/source/binary hashes '
              'and all-layer peaks are in RESULT.json. Layout generation and reproduction instructions '
              'are in ../README.md. Each fixture has its own frozen sample and measured mesh '
              'error; do not transfer an error estimate between fixtures.', '']
    return '\n'.join(lines)


def execution_commit():
    """Best-effort provenance; never part of the evaluator identity."""
    build_sha = os.environ.get('BUILD_SHA', '').strip()
    if build_sha:
        return build_sha
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[1],
            text=True, stderr=subprocess.DEVNULL).strip() or 'unknown'
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=('ascend910', 'micro150'), default='ascend910')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--n', type=int, default=24)
    parser.add_argument('--layouts', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--freeze-only', action='store_true')
    parser.add_argument('--grids', nargs='+', type=int, default=[16, 32, 64])
    parser.add_argument('--layout-ids', nargs='+')
    parser.add_argument('--check', type=Path, help='validate an existing RESULT.json without simulation')
    args = parser.parse_args(argv)
    if args.check:
        errors = check_result(json.loads(args.check.read_text(encoding='utf-8')), args.check.parent)
        print(json.dumps({'ok': not errors, 'errors': errors}))
        return int(bool(errors))
    path = args.layouts or EVIDENCE_ROOT / args.fixture / 'layouts.json'
    if args.freeze_only:
        freeze_layouts(path, make_layout_set(args.fixture, args.seed, args.n))
        print(f'Frozen {path}; commit this file and its .sha256 before evaluation.')
        return 0
    frozen, sha = load_layouts(path)
    if (frozen['fixture'], frozen['seed'], frozen['n']) != (args.fixture, args.seed, args.n):
        raise ValueError('CLI fixture/seed/n do not match frozen layouts')
    output = args.output_dir or path.parent
    if (output / 'RESULT.json').exists() or (output / 'REPORT.md').exists():
        raise FileExistsError('results already exist; use a new --output-dir for reruns')
    revision = execution_commit()
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', revision):
        raise ValueError('mesh execution requires a full source revision; set BUILD_SHA before evaluation')
    result = asyncio.run(evaluate_layouts(frozen, args.grids, args.layout_ids,
                                         evidence_dir=output, layouts_sha256=sha))
    result['execution_commit'] = revision
    errors = check_result(result, output)
    if errors:
        raise ValueError('; '.join(errors))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'RESULT.json').write_bytes(_json_bytes(result))
    (output / 'REPORT.md').write_text(report(result), encoding='utf-8')
    print(json.dumps({'result': str(output / 'RESULT.json'), 'summary': result['summary']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
