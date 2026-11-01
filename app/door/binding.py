"""Sign or check the door's runtime binding: the exact manifest it serves and the grant it may spend (warden).

    python -m app.door.binding sign --key OPERATOR.pem --manifest manifest.json --grant grant.json --out binding.json
    python -m app.door.binding check --manifest manifest.json --binding binding.json

The binding is {"schema": "sentilab-door-binding/1", "manifest_id", "grant": {...}} signed with Ed25519 over the
gate-zero canonical bytes (sundai_hotspot.gate0_anchor.sign). The door verifies it with the operator key SLAB-049
pins, so only that key opens it. `check` runs the door's own Policy over the two files and prints every reason the
door would stay closed now; it never prints a key.

grant.json: {"grant": "<the manifest's refs.grant>", "cpu_cap_s": 3600, "token_cpu_s": 30, "parallel": 4,
"run_reserve_cpu_s": <the scorer's whole-container envelope per run>, "not_before": "<UTC>", "not_after": "<UTC>",
"enforcement_evidence_sha256": "<the scorer's whole-container cutoff evidence>"}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from open_proposals.contract import canonical as hashes

from .policy import BINDING_SCHEMA, Grant, Policy, pinned_operator_key, verify_binding


def sign(key_path: Path, manifest_path: Path, grant_path: Path, out_path: Path) -> dict:
    from sundai_hotspot import gate0_anchor

    key = gate0_anchor.load_private_key(key_path)
    manifest = json.loads(manifest_path.read_bytes())
    grant = json.loads(grant_path.read_bytes())
    Grant.parse(grant)
    signed = gate0_anchor.sign(key, {"schema": BINDING_SCHEMA, "manifest_id": hashes.manifest_id(manifest),
                                     "grant": grant})
    public = gate0_anchor.public_key_hex(key)
    verify_binding(signed, public)
    out_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        pinned = public == pinned_operator_key()
    except ValueError:
        pinned = False
    return {"manifest_id": signed["manifest_id"], "signed_with_pinned_operator_key": pinned}


def check(manifest_path: Path, binding_path: Path, now: float | None = None) -> dict:
    manifest = json.loads(manifest_path.read_bytes())
    policy = Policy(manifest=manifest, binding=json.loads(binding_path.read_bytes()), admission_switch="open",
                    k_challenge=b"\x00" * 32)
    found, final = policy.admission(time.time() if now is None else now)
    return {"manifest_id": hashes.manifest_id(manifest), "problems": policy.problems,
            "admission_if_switched_open": [item["code"] for item in found], "window_over": final}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.door.binding")
    sub = parser.add_subparsers(dest="command", required=True)
    signing = sub.add_parser("sign")
    signing.add_argument("--key", type=Path, required=True)
    signing.add_argument("--manifest", type=Path, required=True)
    signing.add_argument("--grant", type=Path, required=True)
    signing.add_argument("--out", type=Path, required=True)
    checking = sub.add_parser("check")
    checking.add_argument("--manifest", type=Path, required=True)
    checking.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "sign":
        print(json.dumps(sign(args.key, args.manifest, args.grant, args.out), indent=2))
        return 0
    report = check(args.manifest, args.binding)
    print(json.dumps(report, indent=2))
    return 0 if not report["problems"] and not report["admission_if_switched_open"] else 1


if __name__ == "__main__":
    sys.exit(main())
