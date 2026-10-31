"""Summarize retained phase measurements or freeze a fitting declaration.

These commands never run thermal solves. Measured calls must first be collected
under a separately authorized and supervised profiling grant.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from sundai_controller.evidence_profile import AdmissionRefused, build_profile, freeze


def summarize(identity_path, record_paths, output_path):
    """Keep canonical records plus the exact source-file digest and reference."""
    identity = json.loads(Path(identity_path).read_bytes())
    records, sources = [], []
    paths = []
    for path in map(Path, record_paths):
        paths.extend(sorted(path.glob('*.json')) if path.is_dir() else [path])
    if not paths:
        raise AdmissionRefused('no retained call records found')
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise AdmissionRefused('duplicate retained call record paths')
    for path in resolved:
        contents = path.read_bytes()
        data = json.loads(contents)
        items = data if isinstance(data, list) else [data]
        start = len(records)
        records.extend(items)
        sources.append({'path': str(path), 'sha256': hashlib.sha256(contents).hexdigest(),
                        'first_record_index': start, 'record_count': len(items)})
    profile = build_profile(records, identity)
    profile['record_sources'] = sources
    encoded = (json.dumps(profile, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    with Path(output_path).open('xb') as stream:
        stream.write(encoded)
    return {'path': str(Path(output_path).resolve()), 'sha256': hashlib.sha256(encoded).hexdigest(),
            'sample_count': profile['sample_count'], 'record_count': profile['record_count'],
            'excluded_count': profile['excluded_count'],
            'usable_for_admission': profile['usable_for_admission']}


def freeze_declaration(prereg_path, budget_path, output_path):
    """Read current catalog identities and ledger capacity without starting a worker."""
    from sundai_controller.headroom_evidence import available_cpu, execution_identity, check_declared_calls
    from sundai_controller.evidence_profile import declared_calls
    from sundai_hotspot.tap_oracle import HotSpotOracle
    prereg_path, budget_path = Path(prereg_path), Path(budget_path)
    contents = prereg_path.read_bytes()
    prereg = json.loads(contents)
    schedule = declared_calls(prereg)
    oracle = HotSpotOracle(prereg['grid'], prereg['grid'], fixture=prereg['fixture'])
    identity = execution_identity(oracle)
    # Do not freeze against a ledger that an active run can be changing.
    with budget_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(budget_path.read_bytes())
        check_declared_calls(prereg, state, schedule['declared_calls'])
        frozen = freeze(prereg_path, output_path, available_cpu(prereg, state),
                        identity=identity, contents=contents)
    return frozen['evidence_profile_admission']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    summarize_parser = commands.add_parser('summarize', help='summarize existing call records; no solves')
    summarize_parser.add_argument('--identity', type=Path, required=True)
    summarize_parser.add_argument('--records', type=Path, nargs='+', required=True,
                                  help='JSON call records, JSON lists, or directories of call JSON files')
    summarize_parser.add_argument('--out', type=Path, required=True)
    freeze_parser = commands.add_parser('freeze', help='refuse or freeze a declaration; no solves')
    freeze_parser.add_argument('--prereg', type=Path, required=True)
    freeze_parser.add_argument('--budget', type=Path, required=True)
    freeze_parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'summarize':
            result = summarize(args.identity, args.records, args.out)
        else:
            result = freeze_declaration(args.prereg, args.budget, args.out)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
