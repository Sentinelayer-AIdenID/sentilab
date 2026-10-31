"""Python port of the immutable ResultCheck v0.2 reference; no runtime Node.

The public receipt is resultcheck.receipt.v2. Errors and flags retain the
contract's codes; neither notes nor other arbitrary submitted text is echoed.
"""
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
import math
import os
import re
import stat
import struct
import unicodedata

CHECKER_VERSION = 'resultcheck-ref-0.2'
SCHEMA_VERSION = 'resultcheck.receipt.v2'
SCOPE = ('Checks submitted-data consistency and arithmetic only. Does not certify '
         'that measurements are authentic or that any model is physically valid.')
MAX_BYTES = 1024 * 1024
# Transport intake ceiling, separate from the contract's 1 MiB parsing cap.
# Bounded oversized files still receive the contract's complete raw-byte hash.
MAX_FILE_BYTES = 16 * MAX_BYTES
MAX_PAIRS = 10000
MAX_DEPTH = 8
MAX_VALUES = 200000
ID_PATTERN = re.compile(r'[A-Za-z0-9._:-]{1,128}\Z')
ESTIMANDS = ('mean_difference', 'percent_change_of_means', 'mean_of_percent_changes')
TEMPERATURE_WORDS = {'', 'c', 'f', 'k', 'r', 'celsius', 'centigrade', 'fahrenheit',
                     'kelvin', 'kelvins', 'rankine'}
# ECMAScript whitespace, rather than Python's broader Unicode \s.
SPACE = '\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def _number(value):
    """JSON.stringify's binary64 spelling, including its fixed/exponent cutoffs."""
    try:
        value = float(value)
    except OverflowError:
        return 'null'
    if not math.isfinite(value):
        return 'null'
    if value == 0:
        return '0'
    text = repr(value).lower()
    mantissa, _, exponent = text.partition('e')
    if exponent:
        power = int(exponent)
        if 1e-6 <= abs(value) < 1e21:
            return format(Decimal(text), 'f')
        return mantissa.removesuffix('.0') + 'e' + ('+' if power >= 0 else '-') + str(abs(power))
    return text.removesuffix('.0')


def _string(value):
    value = value.encode('utf-16-le', errors='surrogatepass').decode('utf-16-le', errors='surrogatepass')
    text = json.dumps(value, ensure_ascii=False)
    # JSON.stringify escapes lone UTF-16 surrogates but emits ordinary Unicode.
    return ''.join(f'\\u{ord(c):04x}' if 0xD800 <= ord(c) <= 0xDFFF else c for c in text)


def canonical(value):
    """Canonical JSON used both on the wire and for the contract's SHA-256 seals."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return '[' + ','.join(canonical(x) for x in value) + ']'
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode('utf-16-be', errors='surrogatepass'))
        return '{' + ','.join(_string(k) + ':' + canonical(value[k]) for k in keys) + '}'
    raise TypeError('ResultCheck accepts JSON values only')


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _seal(receipt):
    return {**receipt, 'receipt_hash': _sha(canonical(receipt))}


def _base(request_hash, request_id=None, notes_present=False):
    return dict(schema_version=SCHEMA_VERSION, checker_version=CHECKER_VERSION,
                scope=SCOPE, request_hash=request_hash, request_id=request_id,
                notes_present=notes_present)


def _rejected(errors, request_hash, request_id=None, notes_present=False):
    return _seal(dict(**_base(request_hash, request_id, notes_present), status='rejected',
                      errors=errors, counts=None, flags=[], statistics=None, claim_result=None))


def _structure_error(request):
    stack = [(request, 1)]
    values = 0
    while stack:
        value, depth = stack.pop()
        values += 1
        if values > MAX_VALUES:
            return 'request_too_large'
        if not isinstance(value, (dict, list)):
            continue
        if depth > MAX_DEPTH:
            return 'request_too_deep'
        if isinstance(value, dict):
            # Object.values visits array-index keys first, then insertion order.
            indices = sorted((k for k in value if isinstance(k, str) and
                              re.fullmatch(r'0|[1-9][0-9]{0,9}', k) and int(k) < 4294967295), key=int)
            index_keys = set(indices)
            children = [value[k] for k in indices] + [v for k, v in value.items() if k not in index_keys]
        else:
            children = value
        stack.extend((child, depth + 1) for child in children)
    return None


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _id(value):
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _length(value):
    return len(value.encode('utf-16-le', errors='surrogatepass')) // 2


def _only(value, keys):
    return isinstance(value, dict) and all(k in keys for k in value)


def _validate(request):
    if not isinstance(request, dict):
        return ['not_an_object']
    if len(canonical(request).encode('utf-8')) > MAX_BYTES:
        return ['request_too_large']
    errors = []
    if not _only(request, ('schema_version', 'request_id', 'metric', 'pairs', 'claim', 'notes')):
        errors.append('unknown_field')
    if request.get('schema_version') != 'resultcheck.request.v2':
        errors.append('bad_schema_version')
    if not _id(request.get('request_id')):
        errors.append('bad_request_id')
    metric = request.get('metric')
    if (not _only(metric, ('name', 'unit', 'direction', 'scale', 'tie_tolerance'))
            or not isinstance(metric.get('name'), str) or not 1 <= _length(metric['name']) <= 128
            or not isinstance(metric.get('unit'), str) or _length(metric['unit']) > 32
            or metric.get('direction') not in ('lower_is_better', 'higher_is_better')
            or ('scale' in metric and metric['scale'] not in ('ratio', 'interval'))
            or ('tie_tolerance' in metric and
                (not _finite(metric['tie_tolerance']) or metric['tie_tolerance'] < 0))):
        errors.append('bad_metric')
    pairs = request.get('pairs')
    if not isinstance(pairs, list):
        errors.append('bad_pairs')
    elif len(pairs) > MAX_PAIRS:
        errors.append('too_many_pairs')
    else:
        grouped = 0
        pair_errors = ('bad_pairs', 'bad_pair_id', 'bad_pair_value', 'bad_pair_group')
        for pair in pairs:
            if not _only(pair, ('id', 'baseline', 'candidate', 'group')):
                errors.append('bad_pairs')
                break
            if not _id(pair.get('id')):
                errors.append('bad_pair_id')
                break
            if any(k not in pair or (pair[k] is not None and not _finite(pair[k]))
                   for k in ('baseline', 'candidate')):
                errors.append('bad_pair_value')
                break
            if 'group' in pair:
                if not _id(pair['group']):
                    errors.append('bad_pair_group')
                    break
                grouped += 1
        if 0 < grouped < len(pairs) and not any(e in errors for e in pair_errors):
            errors.append('bad_pair_group')
    if 'claim' in request:
        claim = request['claim']
        if (not _only(claim, ('estimand', 'value', 'tolerance'))
                or claim.get('estimand') not in ESTIMANDS or not _finite(claim.get('value'))
                or ('tolerance' in claim and
                    (not _finite(claim['tolerance']) or claim['tolerance'] < 0))):
            errors.append('bad_claim')
    if 'notes' in request and (not isinstance(request['notes'], str) or _length(request['notes']) > 4096):
        errors.append('bad_notes')
    return errors


def _sum(values):
    # Python 3.12 sum compensates rounding; JS reduce adds left-to-right.
    total = 0.0
    for value in values:
        total += value
    return total


def _mean(values):
    return _sum(values) / len(values)


def _round6(value):
    if not math.isfinite(value) or abs(value) >= 1e21:
        return value
    with localcontext() as context:
        context.prec = 50
        rounded = float(Decimal.from_float(float(value)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
    return 0 if rounded == 0 else rounded


# The following two restricted-domain routines are adapted from fdlibm, as
# used by Node 22's V8 src/base/ieee754.cc. Host libm can differ by one ulp,
# changing toFixed(6) at half-way sign-test values (e.g. 6 wins / 2 losses).
# Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
# Developed at SunSoft, a Sun Microsystems, Inc. business.
# Permission to use, copy, modify, and distribute this software is freely
# granted, provided that this notice is preserved.
_LN2_HI = 6.93147180369123816490e-01
_LN2_LO = 1.90821492927058770002e-10


def _integer_log(value):
    """fdlibm log for positive integers used by the bounded sign test."""
    high, low = struct.unpack('>II', struct.pack('>d', float(value)))
    k = (high >> 20) - 1023
    high &= 0x000FFFFF
    adjust = (high + 0x95F64) & 0x100000
    x = struct.unpack('>d', struct.pack('>II', high | (adjust ^ 0x3FF00000), low))[0]
    k += adjust >> 20
    f = x - 1.0
    if (0x000FFFFF & (2 + high)) < 3:
        if f == 0:
            return k * _LN2_HI + k * _LN2_LO
        r = f * f * (0.5 - 0.33333333333333333 * f)
        return f - r if k == 0 else k * _LN2_HI - ((r - k * _LN2_LO) - f)
    t = f / (2.0 + f)
    z = t * t
    w = z * z
    t1 = w * (3.999999999940941908e-01 + w * (2.222219843214978396e-01 + w * 1.531383769920937332e-01))
    t2 = z * (6.666666666666735130e-01 + w * (2.857142874366239149e-01 + w *
              (1.818357216161805012e-01 + w * 1.479819860511658591e-01)))
    r = t2 + t1
    if ((high - 0x6147A) | (0x6B851 - high)) > 0:
        half_square = 0.5 * f * f
        if k == 0:
            return f - (half_square - t * (half_square + r))
        return k * _LN2_HI - ((half_square - (t * (half_square + r) + k * _LN2_LO)) - f)
    return f - t * (f - r) if k == 0 else k * _LN2_HI - ((t * (f - r) - k * _LN2_LO) - f)


def _negative_exp(x):
    """fdlibm exp for the nonpositive log probabilities in the sign test."""
    if x < -7.45133219101941108420e+02:
        return 0.0
    high = struct.unpack('>II', struct.pack('>d', x))[0] & 0x7FFFFFFF
    k, hi, lo = 0, 0.0, 0.0
    if high > 0x3FD62E42:
        if high < 0x3FF0A2B2:
            hi, lo, k = x + _LN2_HI, -_LN2_LO, -1
        else:
            k = int(1.44269504088896338700e+00 * x - 0.5)
            hi, lo = x - k * _LN2_HI, k * _LN2_LO
        x = hi - lo
    elif high < 0x3E300000:
        return 1.0 + x
    t = x * x
    c = x - t * (1.66666666666666019037e-01 + t * (-2.77777777770155933842e-03 + t *
                 (6.61375632143793436117e-05 + t * (-1.65339022054652515390e-06 + t * 4.13813679705723846039e-08))))
    if k == 0:
        return 1.0 - ((x * c) / (c - 2.0) - x)
    y = 1.0 - ((lo - (x * c) / (2.0 - c)) - hi)
    return y * math.ldexp(1.0, k) if k >= -1021 else y * math.ldexp(1.0, k + 1000) * 9.33263618503218878990e-302


def _sign_test(wins, losses):
    n, k = wins + losses, max(wins, losses)
    log_coefficient, tail = 0.0, 0.0
    for i in range(n + 1):
        if i >= k:
            tail += _negative_exp(log_coefficient - n * 0.6931471805599453)
        if i < n:
            log_coefficient += _integer_log(n - i) - _integer_log(i + 1)
    return min(1, 2 * tail)


def _temperature(unit):
    folded = unicodedata.normalize('NFKC', unit).lower()
    return re.sub(r'degrees?|deg|[' + SPACE + r'_.\-°º]', '', folded) in TEMPERATURE_WORDS


def _claim(claim, metric, units, improvements, flags):
    base = dict(estimand=claim['estimand'], claimed=claim['value'])

    def refuse(flag):
        flags.add(flag)
        return dict(**base, recomputed=None, difference=None, tolerance=None,
                    tolerance_basis=None, outcome='refused')

    if claim['estimand'] == 'mean_difference':
        recomputed = _mean(improvements)
    else:
        if metric.get('scale') != 'ratio' or _temperature(metric['unit']):
            return refuse('invalid_normalization')
        if claim['estimand'] == 'percent_change_of_means':
            mean_baseline = _mean([u['baseline'] for u in units])
            if mean_baseline == 0:
                return refuse('zero_denominator')
            recomputed = _mean(improvements) / abs(mean_baseline) * 100
        else:
            if any(u['baseline'] == 0 for u in units):
                return refuse('zero_denominator')
            recomputed = _mean([d / abs(u['baseline']) for u, d in zip(units, improvements)]) * 100
    declared = 'tolerance' in claim
    tolerance = claim['tolerance'] if declared else max(1e-12, 0.001 * max(abs(recomputed), abs(claim['value'])))
    if not declared and math.isnan(recomputed):
        tolerance = float('nan')  # Math.max propagates NaN; Python max does not.
    difference = abs(recomputed - claim['value'])
    matches = difference <= tolerance + 1e-12
    if not matches:
        flags.add('arithmetic_discrepancy')
    return dict(**base, recomputed=_round6(recomputed), difference=_round6(difference),
                tolerance=_round6(tolerance), tolerance_basis='declared' if declared else 'default_relative',
                outcome='matches' if matches else 'discrepancy')


def check(request):
    """Check a JSON value and return the normative contract receipt."""
    structure = _structure_error(request)
    if structure:
        return _rejected([structure], None)
    request_id = request.get('request_id') if isinstance(request, dict) else None
    request_id = request_id if _id(request_id) else None
    notes_present = isinstance(request, dict) and isinstance(request.get('notes'), str)
    request_hash = _sha(canonical(request))
    errors = _validate(request)
    if errors:
        return _rejected(errors, request_hash, request_id, notes_present)
    receipt = _base(request_hash, request_id, notes_present)
    occurrences = Counter(p['id'] for p in request['pairs'])
    duplicates = sorted(k for k, count in occurrences.items() if count > 1)
    distinct = [p for p in request['pairs'] if occurrences[p['id']] == 1]
    missing = [p for p in distinct if p['baseline'] is None or p['candidate'] is None]
    used = [p for p in distinct if p['baseline'] is not None and p['candidate'] is not None]
    grouped = bool(request['pairs']) and 'group' in request['pairs'][0]
    units = [dict(baseline=float(p['baseline']), candidate=float(p['candidate'])) for p in used]
    if grouped:
        by_group = {}
        for pair in used:
            by_group.setdefault(pair['group'], []).append(pair)
        units = [dict(baseline=_mean([float(p['baseline']) for p in by_group[g]]),
                      candidate=_mean([float(p['candidate']) for p in by_group[g]])) for g in sorted(by_group)]
    flags = set()
    if duplicates:
        flags.add('duplicate_ids')
    if missing:
        flags.add('missing_pairs')
    counts = dict(submitted=len(request['pairs']), duplicates_excluded=len(request['pairs']) - len(distinct),
                  missing_excluded=len(missing), used=len(used), analysis_unit='group' if grouped else 'pair', units=len(units))
    details = dict(duplicate_ids=duplicates, missing_ids=sorted(p['id'] for p in missing))
    if len(units) < 2:
        return _seal(dict(**receipt, status='insufficient_data', errors=[], counts=counts,
                          details=details, flags=sorted(flags), statistics=None, claim_result=None))
    lower = request['metric']['direction'] == 'lower_is_better'
    tie_tolerance = request['metric'].get('tie_tolerance', 0)
    improvements = [u['baseline'] - u['candidate'] if lower else u['candidate'] - u['baseline'] for u in units]
    n = len(improvements)
    average = _mean(improvements)
    ordered = sorted(improvements)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    variance = _sum((d - average) * (d - average) for d in improvements) / (n - 1)
    wins = sum(d > tie_tolerance for d in improvements)
    losses = sum(d < -tie_tolerance for d in improvements)
    enough = wins + losses >= 6
    if not enough:
        flags.add('insufficient_for_inference')
    statistics = dict(mean_improvement=_round6(average), median_improvement=_round6(median),
                      sd_sample=_round6(math.sqrt(variance)), min=_round6(ordered[0]), max=_round6(ordered[-1]),
                      wins=wins, losses=losses, ties=n - wins - losses, tie_tolerance=tie_tolerance,
                      sign_test_p_two_sided=_round6(_sign_test(wins, losses)) if enough else None)
    claim_result = _claim(request['claim'], request['metric'], units, improvements, flags) if 'claim' in request else None
    return _seal(dict(**receipt, status='checked_with_flags' if flags else 'checked', errors=[], counts=counts,
                      details=details, flags=sorted(flags), statistics=statistics, claim_result=claim_result))


def _invalid_constant(_):
    raise ValueError('not_json')


def _parse_deep(text):
    """Iterative fallback when Python's decoder hits its recursion limit.

    Fully validate syntax, including trailing bytes: invalid deep JSON is still
    not_json. The normal structure check supplies the reference's null hash.
    """
    decoder = json.JSONDecoder(parse_int=float, parse_float=float, parse_constant=_invalid_constant)
    root = []
    stack = [(root, 'value', None)]
    index = 0
    while stack:
        parent, state, key = stack.pop()
        while index < len(text) and text[index] in ' \t\r\n':
            index += 1
        char = text[index:index + 1]
        if state == 'end':
            if char:
                raise ValueError('not_json')
            return root[0]
        if state in ('comma_array', 'comma_object'):
            closing = ']' if state == 'comma_array' else '}'
            if char == closing:
                index += 1
                continue
            if char != ',':
                raise ValueError('not_json')
            index += 1
            stack.append((parent, 'value' if closing == ']' else 'key', None))
            continue
        if state in ('key', 'key_or_end'):
            if state == 'key_or_end' and char == '}':
                index += 1
                continue
            if char != '"':
                raise ValueError('not_json')
            key, index = decoder.raw_decode(text, index)
            stack.append((parent, 'colon', key))
            continue
        if state == 'colon':
            if char != ':':
                raise ValueError('not_json')
            index += 1
            stack.append((parent, 'value', key))
            continue
        if state == 'value_or_end' and char == ']':
            index += 1
            continue
        if char == '[':
            value = []
            index += 1
        elif char == '{':
            value = {}
            index += 1
        else:
            value, index = decoder.raw_decode(text, index)
        if parent is root:
            stack.append((parent, 'end', None))
        else:
            stack.append((parent, 'comma_object' if isinstance(parent, dict) else 'comma_array', None))
        if isinstance(parent, dict):
            parent[key] = value
        else:
            parent.append(value)
        if char in ('[', '{'):
            stack.append((value, 'value_or_end' if char == '[' else 'key_or_end', None))
    raise ValueError('not_json')


def check_raw(data):
    """Check UTF-8 bytes (or text), rejecting over 1 MiB before any parsing."""
    text = data if isinstance(data, str) else None
    if text is not None:
        data = text.encode('utf-16-le', errors='surrogatepass').decode('utf-16-le', errors='replace').encode('utf-8')
    request_hash = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_BYTES:
        return _rejected(['request_too_large'], request_hash)
    try:
        if text is None:
            text = data.decode('utf-8')
        try:
            request = json.loads(text, parse_int=float, parse_float=float, parse_constant=_invalid_constant)
        except RecursionError:
            request = _parse_deep(text)
    except (ValueError, UnicodeError):
        return _rejected(['not_json'], request_hash)
    return check(request)


def check_file(file):
    """Check a stable regular file, reading at most its bounded size plus one.

    Unsupported, oversized or changing files raise OSError (a transport error),
    never a contract receipt carrying a misleading partial request hash.
    """
    digest = hashlib.sha256()
    prefix = bytearray()
    size = 0
    # Nonblocking open matters BEFORE fstat: a FIFO can otherwise block here.
    fd = os.open(file, os.O_RDONLY | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise OSError('unsupported ResultCheck file')
        while size <= before.st_size:
            chunk = os.read(fd, min(64 * 1024, before.st_size + 1 - size))
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if size <= MAX_BYTES:
                prefix.extend(chunk)
        after = os.fstat(fd)
        if (size != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ctime_ns != before.st_ctime_ns):
            raise OSError('ResultCheck file changed during intake')
    finally:
        os.close(fd)
    if size > MAX_BYTES:
        return _rejected(['request_too_large'], digest.hexdigest())
    return check_raw(bytes(prefix))


def exit_code(receipt):
    """0: checked, 1: flags/insufficient data, 2: rejected or malformed."""
    return {'checked': 0, 'checked_with_flags': 1, 'insufficient_data': 1, 'rejected': 2}[receipt['status']]


# JS spelling retained for callers translating the reference API.
checkRaw = check_raw
