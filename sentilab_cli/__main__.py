import argparse
import asyncio
import json
import sys
from pathlib import Path


def _write_utf8(message, stream):
    stream.buffer.write(message.encode("utf-8"))
    stream.buffer.flush()


class _ResultCheckParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            _write_utf8(message, file if file is not None else sys.stderr)


async def dispatch(command, context, **arguments):
    from sentilab_core import operations
    if command.startswith("research_"):
        from sentilab_core.research import execute
        return execute(command.removeprefix("research_"), context, **arguments)
    operation = getattr(operations, command)
    result = operation(context, **arguments)
    return await result if hasattr(result, "__await__") else result


def advisory_main():
    from sentilab_core import operations
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


def dataset_main():
    from sentilab_core import operations
    from sentilab_core.dataset import export
    parser = argparse.ArgumentParser(prog="sentilab dataset")
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--output-dir", help="parent of immutable dataset snapshots")
    parser.add_argument("--policy", help="JSON file with heldout_families and run rights grants")
    args = parser.parse_args(sys.argv[2:])
    context = operations.environment_context()
    policy = json.loads(Path(args.policy).read_text()) if args.policy else None
    result = export(context.root, args.run_ids, public_keys=context.public_keys,
                    output_dir=args.output_dir, policy=policy)
    print(json.dumps(result, allow_nan=False))


def research_main():
    from sentilab_core import operations, research

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            # argparse's default diagnostic includes caller-supplied text.
            print(research.dumps({"ok": False, "error": {"code": "invalid_input"}}))
            raise SystemExit(2)

    parser = Parser(prog="sentilab research")
    parser.add_argument("command", choices=["request", "status", "export"])
    parser.add_argument("--ai-off", action="store_true")
    parser.add_argument("--namespace", required=True, help="JSON run_id/arm/family/seed/lab scope")
    parser.add_argument("--question")
    parser.add_argument("--request-id")
    args = parser.parse_args(sys.argv[2:])
    try:
        if len(args.namespace) > research.MAX_BYTES:
            raise ValueError()
        parameters = {"ai_off": args.ai_off, "namespace": json.loads(args.namespace)}
        if args.question is not None:
            parameters["question"] = args.question
        if args.request_id is not None:
            parameters["request_id"] = args.request_id
        context = operations.environment_context()
        result = asyncio.run(dispatch("research_" + args.command, context, **parameters))
    except (ValueError, TypeError, OSError, RecursionError):
        result = {"ok": False, "error": {"code": "invalid_input"}}
    print(research.dumps(result))
    return 0 if result["ok"] else 2


def main(conductor=False):
    if not conductor and sys.argv[1:2] in (["memory"], ["route"]):
        return advisory_main()
    if not conductor and sys.argv[1:2] == ["resultcheck"]:
        from sentilab_core.resultcheck import canonical, check_file, exit_code
        parser = _ResultCheckParser(prog="sentilab resultcheck")
        parser.add_argument("--root", help="confine file reads to this directory (requires Linux procfs)")
        parser.add_argument("file", help="UTF-8 ResultCheck v2 JSON file")
        args = parser.parse_args(sys.argv[2:])
        try:
            receipt = check_file(args.file, root=args.root)
        except Exception:
            # Intake failures, including unavailable platform operations, must
            # not escape as exit 1: that code denotes a completed flagged check.
            _write_utf8(canonical({"error": {"code": "file_unreadable"}}) + "\n", sys.stdout)
            raise SystemExit(2)
        _write_utf8(canonical(receipt) + "\n", sys.stdout)
        raise SystemExit(exit_code(receipt))
    if not conductor and sys.argv[1:2] == ["research"]:
        return research_main()
    if not conductor and sys.argv[1:2] == ["dataset"]:
        return dataset_main()
    from sentilab_core import operations
    from sentilab_core.budget import Limits
    parser = argparse.ArgumentParser(prog="sentilab" if not conductor else "sentilab_core.conductor")
    if not conductor:
        parser.add_argument("namespace", choices=["live", "dataset", "research", "resultcheck"],
                            help="use dataset --help for export options or resultcheck <file> for offline checking")
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
        from sentilab_core.ledger import replay
        from sentilab_core.envelope import canonical
        rows = replay(context.root, args.run_id, public_keys=context.public_keys)["prefix"]
        Path(args.export).write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    sys.exit(main())
