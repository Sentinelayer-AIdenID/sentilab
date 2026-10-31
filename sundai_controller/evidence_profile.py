"""Measured phase forecasts and refuse-to-start admission for SLAB-050.

Mean phase costs plus an explicit reserve are a forecast, never a hard bound.
The independent lifetime meter and stop remain necessary after admission.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics


SCHEMA = 'slab-050-phase-profile-v1'
PHASES = ('generate', 'solve', 'worker_startup', 'teardown_reap', 'archive', 'overhead')
IDENTITY_FIELDS = ('fixture', 'grid', 'binary_sha256', 'config_sha256', 'source_sha256', 'image_identity')


class AdmissionRefused(ValueError):
    """A profile or declaration cannot support a new allocation."""


def _number(value, label, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise AdmissionRefused(f'{label} must be finite and {"positive" if positive else "nonnegative"}')
    return float(value)


def _count(value, label, *, positive=False):
    if type(value) is not int or value < 0 or (positive and value == 0):
        raise AdmissionRefused(f'{label} must be a {"positive" if positive else "nonnegative"} integer')
    return value


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _identity(value):
    if not isinstance(value, dict):
        raise AdmissionRefused('profile identity must be an object')
    missing = [key for key in IDENTITY_FIELDS if value.get(key) in (None, '', {}, [])]
    if missing:
        raise AdmissionRefused('profile identity is missing: ' + ', '.join(missing))
    _count(value['grid'], 'identity grid', positive=True)
    if not isinstance(value['fixture'], str):
        raise AdmissionRefused('identity fixture must be a string')
    def digest(item):
        return (isinstance(item, str) and len(item) == 64 and
                all(character in '0123456789abcdef' for character in item))
    for field in ('binary_sha256', 'config_sha256'):
        if not digest(value[field]):
            raise AdmissionRefused(f'identity {field} must be a SHA-256 digest')
    source = value['source_sha256']
    if not (digest(source) or (isinstance(source, dict) and source and
                              all(isinstance(name, str) and digest(item) for name, item in source.items()))):
        raise AdmissionRefused('identity source_sha256 must be a digest or per-file digest map')
    # source_sha256 may be a per-file digest mapping. Image identity may explicitly
    # record unavailable host metadata and the retained build-description digest.
    try:
        return json.loads(_json_bytes(value))
    except (TypeError, ValueError) as exc:
        raise AdmissionRefused('identity must contain finite JSON values') from exc


def declared_calls(prereg):
    """Count maximum oracle calls from the runner's actual lane convention.

    Reducer calls include fresh reproductions. Diagnostics only search. Long-SA
    max_evaluations_per_restart already includes its final fresh reproduction.
    No-op savings are deliberately not assumed before the work is performed.
    """
    cheap = prereg.get('reducer_methods', prereg.get('cheap_methods', {}))
    long = prereg.get('long_sa', {})
    methods = cheap.get('methods')
    seeds = cheap.get('seeds')
    long_seeds = long.get('seeds')
    diagnostics = prereg.get('extra_diagnostics', {}).get('methods', [])
    for value, label, required in ((methods, 'reducer methods', True),
                                   (seeds, 'cheap seeds', True),
                                   (long_seeds, 'long seeds', True),
                                   (diagnostics, 'diagnostic methods', False)):
        if not isinstance(value, list) or (required and not value):
            raise AdmissionRefused(f'{label} must be {"a nonempty" if required else "a"} list')
    search = _count(cheap.get('search_evaluations_per_method', cheap.get('evaluations_per_method')),
                    'cheap search evaluations', positive=True)
    reproduction = _count(cheap.get('reproduction_evaluations_per_method', 0),
                          'cheap reproduction evaluations')
    maximum = _count(long.get('max_evaluations_per_restart'), 'long maximum evaluations', positive=True)
    long_reproduction = _count(long.get('reproduction_evaluations_per_restart', 0),
                               'long reproduction evaluations')
    if long_reproduction >= maximum:
        raise AdmissionRefused('long reproduction evaluations leave no search evaluations')
    if 'search_evaluations_per_restart' in long:
        long_search = _count(long['search_evaluations_per_restart'], 'long search evaluations', positive=True)
        if long_search + long_reproduction != maximum:
            raise AdmissionRefused('long search plus reproduction differs from maximum evaluations')
    reducer_calls = len(methods) * len(seeds) * (search + reproduction)
    diagnostic_calls = len(diagnostics) * len(seeds) * search
    long_calls = len(long_seeds) * maximum
    return {'reducer_calls': reducer_calls, 'diagnostic_calls': diagnostic_calls,
            'long_calls': long_calls, 'declared_calls': reducer_calls + diagnostic_calls + long_calls}


def build_profile(records, identity):
    """Retain every outcome/charge, marking incomplete profiles inadmissible.

    Call history is embedded alongside its canonical digest and raw artifact refs;
    no filtering can make a failed or partially measured run appear complete.
    """
    bound_identity = _identity(identity)
    retained, samples, exclusions = [], [], []
    total_charge = 0.0
    unknown_charge_count = 0
    for index, original in enumerate(records):
        if not isinstance(original, dict):
            raise AdmissionRefused(f'record {index} must be an object')
        record = json.loads(_json_bytes(original))
        refs = {key: record[key] for key in ('raw_directory', 'raw_output_directory', 'raw_manifest', 'raw_manifest_sha256',
                                           'raw_artifacts', 'artifact_directory') if key in record}
        retained.append({'record_sha256': hashlib.sha256(_json_bytes(record)).hexdigest(),
                         'raw_artifact_refs': refs, 'record': record})
        reasons = []
        try:
            charge = _number(record.get('metered_cpu_seconds'), f'record {index} metered CPU')
            total_charge += charge
        except AdmissionRefused as exc:
            reasons.append(str(exc))
            charge = None
            unknown_charge_count += 1
        if record.get('error') or not isinstance(record.get('result'), dict):
            reasons.append('missing successful result or error outcome')
        if (record.get('cleanup_error') or record.get('status', 'completed') != 'completed' or
                record.get('profile_complete') is False):
            reasons.append('incomplete call or cleanup outcome')
        if record.get('reaping_confirmed') is False:
            reasons.append('reaping not confirmed')
        phases = record.get('phase_timings', {})
        measured = {}
        for phase in PHASES:
            try:
                values = phases.get(phase, {})
                measured[phase] = {
                    metric: _number(values.get(metric), f'record {index} {phase} {metric}')
                    for metric in ('cpu_seconds', 'wall_seconds')}
            except (AdmissionRefused, AttributeError) as exc:
                reasons.append(str(exc))
        if len(measured) == len(PHASES) and charge is not None:
            if sum(value['cpu_seconds'] for value in measured.values()) + 1e-9 < charge:
                reasons.append('phase CPU omits part of metered charge')
        if reasons:
            exclusions.append({'record_index': index, 'reasons': reasons})
        else:
            samples.append(measured)
    means = {
        phase: {f'mean_{metric}': statistics.fmean(sample[phase][metric] for sample in samples)
                for metric in ('cpu_seconds', 'wall_seconds')}
        for phase in PHASES} if samples else {}
    return {'schema': SCHEMA, 'identity': bound_identity, 'sample_count': len(samples),
            'record_count': len(retained), 'excluded_count': len(exclusions),
            'usable_for_admission': bool(samples) and not exclusions,
            'phase_means': means, 'metered_cpu_seconds': total_charge,
            'unknown_charge_count': unknown_charge_count, 'excluded_records': exclusions,
            'records': retained,
            'forecast_policy': 'Measured phase means plus explicit reserve; forecast, not a bound. '
                               'Independent CPU metering and stopping are still required.'}


def _validate_measurements(profile, identity):
    """A stale or edited summary must not understate its embedded measurements."""
    entries = profile.get('records')
    if not isinstance(entries, list) or not entries:
        raise AdmissionRefused('profile must retain measured call records')
    records = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('record'), dict):
            raise AdmissionRefused('profile contains an invalid measured call record')
        record = entry['record']
        try:
            digest = hashlib.sha256(_json_bytes(record)).hexdigest()
        except (TypeError, ValueError) as exc:
            raise AdmissionRefused('profile measured record must contain finite JSON values') from exc
        if entry.get('record_sha256') != digest:
            raise AdmissionRefused('profile measured record SHA-256 differs')
        records.append(record)
    rebuilt = build_profile(records, identity)
    for field in ('sample_count', 'record_count', 'excluded_count', 'usable_for_admission',
                  'phase_means', 'metered_cpu_seconds', 'unknown_charge_count'):
        if profile.get(field) != rebuilt[field]:
            raise AdmissionRefused(f'profile {field} differs from measured call records')
    if not rebuilt['usable_for_admission']:
        raise AdmissionRefused('incomplete/error measured call records cannot admit a run')


def admission(prereg, profile, available_cpu_seconds, *, identity=None):
    """Return forecast arithmetic, or refuse with the exact CPU shortfall."""
    available = _number(available_cpu_seconds, 'available CPU seconds')
    if not isinstance(profile, dict) or profile.get('schema') != SCHEMA:
        raise AdmissionRefused(f'profile schema must be {SCHEMA}')
    bound = _identity(profile.get('identity'))
    if bound['fixture'] != prereg.get('fixture') or bound['grid'] != prereg.get('grid'):
        raise AdmissionRefused('profile fixture/grid identity differs from preregistration')
    if identity is None:
        raise AdmissionRefused('current executable/source/image identity is required for admission')
    if bound != _identity(identity):
        raise AdmissionRefused('profile identity differs from current executable/source/image identity')
    _count(profile.get('sample_count'), 'profile sample_count', positive=True)
    if profile.get('usable_for_admission') is not True or profile.get('excluded_count') != 0:
        raise AdmissionRefused('incomplete/error phase profile cannot admit a run')
    per_phase = {}
    for phase in PHASES:
        values = profile.get('phase_means', {}).get(phase, {})
        per_phase[phase] = _number(values.get('mean_cpu_seconds'), f'{phase} mean CPU seconds')
        _number(values.get('mean_wall_seconds'), f'{phase} mean wall seconds')
    per_call = sum(per_phase.values())
    _number(per_call, 'total measured per-call CPU seconds', positive=True)
    _validate_measurements(profile, bound)
    declaration = prereg.get('evidence_profile')
    if not isinstance(declaration, dict):
        raise AdmissionRefused('preregistration requires evidence_profile with an explicit reserve')
    reserve = _number(declaration.get('reserve_cpu_seconds'), 'reserve_cpu_seconds', positive=True)
    reason = declaration.get('reserve_reason')
    if not isinstance(reason, str) or not reason.strip():
        raise AdmissionRefused('reserve_reason must state the reason for the reserve')
    schedule = declared_calls(prereg)
    if 'declared_calls' in declaration:
        count = _count(declaration['declared_calls'], 'evidence_profile declared_calls', positive=True)
        if count != schedule['declared_calls']:
            raise AdmissionRefused(f'declared_calls {count} differs from schedule {schedule["declared_calls"]}')
    forecast = schedule['declared_calls'] * per_call
    required = forecast + reserve
    _number(required, 'forecast plus reserve', positive=True)
    if required > available:
        raise AdmissionRefused(
            f'CPU cap shortfall: {required - available:.9f} CPU-s; declared {schedule["declared_calls"]} '
            f'calls x {per_call:.9f} measured CPU-s + {reserve:.9f} reserve = '
            f'{required:.9f} CPU-s required, {available:.9f} CPU-s available')
    return {'schema': 'slab-050-admission-v1', 'admitted': True, **schedule,
            'phase_mean_cpu_seconds': per_phase, 'measured_cpu_seconds_per_call': per_call,
            'forecast_cpu_seconds': forecast, 'reserve_cpu_seconds': reserve,
            'reserve_reason': reason, 'required_cpu_seconds': required,
            'available_cpu_seconds': available, 'headroom_cpu_seconds': available - required,
            'identity': bound, 'sample_count': profile['sample_count'],
            'forecast_is_bound': False, 'requires_runtime_stop': True}


def load_admission(prereg, prereg_path, available_cpu_seconds, *, identity=None, required=True):
    """Hash and parse the same profile bytes, resolving its path beside prereg."""
    declaration = prereg.get('evidence_profile')
    if declaration is None and not required:
        return None
    if not isinstance(declaration, dict):
        raise AdmissionRefused('measured evidence_profile is required before freeze or start')
    name, digest = declaration.get('path'), declaration.get('sha256')
    if not isinstance(name, str) or not name:
        raise AdmissionRefused('evidence_profile path is required')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise AdmissionRefused('evidence_profile sha256 must be a lowercase SHA-256 digest')
    path = Path(prereg_path).resolve().parent / name
    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise AdmissionRefused(f'cannot read measured evidence profile: {exc}') from exc
    measured_digest = hashlib.sha256(contents).hexdigest()
    if measured_digest != digest:
        raise AdmissionRefused('evidence_profile SHA-256 differs from declaration')
    try:
        profile = json.loads(contents)
    except (ValueError, UnicodeError) as exc:
        raise AdmissionRefused('evidence_profile is not valid JSON') from exc
    report = admission(prereg, profile, available_cpu_seconds, identity=identity)
    return dict(report, profile_sha256=measured_digest, profile_path=str(path.resolve()))


def freeze(prereg_path, output_path, available_cpu_seconds, *, identity=None, contents=None):
    """Write one immutable snapshot only after measured admission succeeds."""
    contents = Path(prereg_path).read_bytes() if contents is None else contents
    prereg = json.loads(contents)
    report = load_admission(prereg, prereg_path, available_cpu_seconds, identity=identity)
    frozen = dict(prereg, evidence_profile_admission=report,
                  source_prereg_sha256=hashlib.sha256(contents).hexdigest())
    # An absolute reference keeps admission bound when the snapshot is elsewhere.
    frozen['evidence_profile'] = dict(prereg['evidence_profile'], path=report['profile_path'])
    encoded = json.dumps(frozen, indent=2, sort_keys=True, allow_nan=False) + '\n'
    with Path(output_path).open('x', encoding='utf-8') as stream:
        stream.write(encoded)
    return frozen
