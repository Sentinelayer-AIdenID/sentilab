"""Record projected evidence from an operator-run, zero-inference CLI probe.

This module never executes a CLI or opens a network connection. Pipe JSON from
an existing configured CLI only after its auth/model-list operation is confirmed
non-billable. Raw input/headers/errors remain in memory and are never printed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

from .admission import _object, public_name, schema
from .ledger import atomic_json

MAX_PROBE_BYTES = 1024 * 1024


def evidence(raw, *, provider, entitlement_source):
    if len(raw) > MAX_PROBE_BYTES:
        raise ValueError("oversize probe")
    data = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(data, dict) or type(data.get("status_code")) is not int:
        raise ValueError("probe needs explicit status code")
    status = data["status_code"]
    # This input contract is a normalized CLI result, not an invented provider API.
    items = data.get("data", [])
    if not isinstance(items, list) or len(items) > 4096:
        raise ValueError("invalid model list")
    models = [public_name(item["id"]) for item in items]
    result = dict(provider=public_name(provider), entitlement_source=public_name(entitlement_source),
                  checked_at=datetime.now(timezone.utc).isoformat(), status_code=status,
                  models=sorted(set(models)))
    Draft202012Validator(schema()["$defs"]["probe"], format_checker=FormatChecker()).validate(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--entitlement-source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_PROBE_BYTES + 1)
        result = evidence(raw, provider=options.provider, entitlement_source=options.entitlement_source)
        atomic_json(options.output, result)
    except Exception:
        print("probe evidence rejected; no raw diagnostics retained", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
