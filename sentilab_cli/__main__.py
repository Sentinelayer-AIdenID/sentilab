import argparse
import asyncio
import json
import sys


async def dispatch(command, context, **arguments):
    from sentilab_core import operations
    operation = getattr(operations, command)
    result = operation(context, **arguments)
    return await result if hasattr(result, "__await__") else result


def main(conductor=False):
    if not conductor and sys.argv[1:2] == ["resultcheck"]:
        from sentilab_core.resultcheck import canonical, check_file, exit_code
        parser = argparse.ArgumentParser(prog="sentilab resultcheck")
        parser.add_argument("--root", help="confine file reads to this directory (requires Linux procfs)")
        parser.add_argument("file", help="UTF-8 ResultCheck v2 JSON file")
        args = parser.parse_args(sys.argv[2:])
        try:
            receipt = check_file(args.file, root=args.root)
        except (OSError, ValueError):
            print(canonical({"error": {"code": "file_unreadable"}}))
            raise SystemExit(2)
        print(canonical(receipt))
        raise SystemExit(exit_code(receipt))
    from sentilab_core import operations
    from sentilab_core.budget import Limits
    parser = argparse.ArgumentParser(prog="sentilab" if not conductor else "sentilab_core.conductor")
    if not conductor:
        parser.add_argument("namespace", choices=["live"], help="live operations; use resultcheck <file> for offline checking")
        parser.add_argument("command", choices=["run", "status", "stop", "verify"])
    parser.add_argument("--ai-off", action="store_true", default=conductor)
    parser.add_argument("--run-id")
    parser.add_argument("--ephemeral", action="store_true", help="explicit local-demo in-memory signer")
    parser.add_argument("--fixture", default="ascend910", choices=["ascend910"])
    parser.add_argument("--margin", type=float, default=0.32)
    parser.add_argument("--grid", type=int, default=16, choices=[16, 32])
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--renew", action="store_true")
    parser.add_argument("--max-evals-per-hour", type=int, default=600)
    parser.add_argument("--max-evals-per-run", type=int, default=200)
    parser.add_argument("--export", help="verified run exported as JSONL (verify only)")
    args = parser.parse_args()
    command = "run" if conductor else args.command
    context = operations.environment_context(ephemeral=args.ephemeral)
    context.options = {"fixture": args.fixture, "margin": args.margin, "grid": args.grid,
                       "deadline": args.deadline,
                       "limits": Limits(evals_per_hour=args.max_evals_per_hour, evals_per_run=args.max_evals_per_run)}
    parameters = {"ai_off": args.ai_off}
    if command in ("run", "status", "verify"):
        parameters["run_id"] = args.run_id
    if command == "run":
        parameters.update(duration=args.duration, interval=args.interval, renew=args.renew)
    result = asyncio.run(dispatch(command, context, **parameters))
    if args.export:
        if command != "verify" or not result["ok"]:
            parser.error("export requires a verified complete run")
        from pathlib import Path
        from sentilab_core.ledger import replay
        from sentilab_core.envelope import canonical
        rows = replay(context.root, args.run_id, public_keys=context.public_keys)["prefix"]
        Path(args.export).write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
