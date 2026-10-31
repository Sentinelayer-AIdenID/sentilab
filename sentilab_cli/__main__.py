import argparse
import asyncio
import json
import sys

from sentilab_core import operations
from sentilab_core.budget import Limits


async def dispatch(command, context, **arguments):
    operation = getattr(operations, command)
    result = operation(context, **arguments)
    return await result if hasattr(result, "__await__") else result


def advisory_main():
    parser = argparse.ArgumentParser(prog="sentilab")
    namespaces = parser.add_subparsers(dest="namespace", required=True)
    memory = namespaces.add_parser("memory", help="scoped ledger-backed memory")
    commands = memory.add_subparsers(dest="command", required=True)
    for command in ("recall", "audit"):
        sub = commands.add_parser(command)
        sub.add_argument("--scope", type=json.loads, required=True, help="exact JSON scope object")
        if command == "recall":
            sub.add_argument("--query", default="")
    route = namespaces.add_parser("route", help="fixture-calibrated advisory routing")
    choice = route.add_mutually_exclusive_group(required=True)
    choice.add_argument("--task", type=json.loads, default=argparse.SUPPRESS, help="JSON candidate and score")
    choice.add_argument("--calibrate", action="store_true", help="report frozen held-out fixture results")
    args = parser.parse_args()
    context = operations.environment_context()
    if args.namespace == "memory":
        command = "memory_" + args.command
        parameters = {"scope": args.scope}
        if args.command == "recall":
            parameters["query"] = args.query
    else:
        command = "route"
        parameters = {"calibrate": True} if args.calibrate else {"task": args.task}
    try:
        result = asyncio.run(dispatch(command, context, **parameters))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, allow_nan=False))


def main(conductor=False):
    if not conductor and sys.argv[1:2] in (["memory"], ["route"]):
        return advisory_main()
    parser = argparse.ArgumentParser(prog="sentilab" if not conductor else "sentilab_core.conductor")
    if not conductor:
        parser.add_argument("namespace", choices=["live"])
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
