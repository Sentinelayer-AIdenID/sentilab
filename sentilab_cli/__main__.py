import argparse
import asyncio
import json
import sys
from pathlib import Path

from sentilab_core.capabilities import cli_commands, exposed
from sentilab_core.transport import check_cli_size, error_receipt


def _write_utf8(message, stream):
    stream.buffer.write(message.encode("utf-8"))
    stream.buffer.flush()


class _ResultCheckParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            _write_utf8(message, file if file is not None else sys.stderr)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        if "not allowed with argument" in message:
            _write_utf8("arguments not allowed together\n", sys.stderr)
        raise ValueError("invalid CLI arguments")


async def dispatch(command, context, **arguments):
    from sentilab_core import operations
    if command in ("memory_recall", "memory_audit", "route"):
        return getattr(operations, command)(context, **arguments)
    if command.startswith("research_"):
        from sentilab_core.research import execute
        return execute(command.removeprefix("research_"), context, **arguments)
    from sentilab_mcp import TOOLS
    result = TOOLS["sentilab_live_" + command](context, **arguments)
    return await result if hasattr(result, "__await__") else result


def advisory_parser():
    parser = SafeParser(prog="sentilab")
    namespaces = parser.add_subparsers(dest="namespace", required=True)
    memory = namespaces.add_parser("memory", help="scoped ledger-backed memory")
    commands = memory.add_subparsers(dest="command", required=True)
    for command in cli_commands("memory"):
        sub = commands.add_parser(command)
        sub.add_argument("--scope", type=json.loads, required=True, help="exact JSON scope object")
        if command == "recall":
            sub.add_argument("--query", default="")
    route = namespaces.add_parser("route", help="fixture-calibrated advisory routing")
    choice = route.add_mutually_exclusive_group(required=True)
    choice.add_argument("--task", type=json.loads, default=argparse.SUPPRESS, help="JSON candidate and score")
    choice.add_argument("--calibrate", action="store_true", help="report frozen held-out fixture results")
    return parser


def advisory_main(*, context=None):
    from sentilab_core import operations
    from sentilab_core.execution import admit, recorded_call
    args = advisory_parser().parse_args()
    if args.namespace == "memory":
        capability = "memory." + args.command
        tool = "sentilab_memory_" + args.command
        parameters = {"scope": args.scope}
        if args.command == "recall":
            parameters["query"] = args.query
    else:
        capability = "memory.route"
        tool = "sentilab_route"
        parameters = {"calibrate": True} if args.calibrate else {"task": args.task}
    admit(tool, parameters)
    context = context if context is not None else operations.environment_context()
    result = asyncio.run(recorded_call(context, capability, parameters))
    print(json.dumps(result, allow_nan=False))


def dataset_parser():
    parser = SafeParser(prog="sentilab dataset")
    parser.add_argument("command", choices=cli_commands("dataset"))
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--output-dir", help="parent of immutable dataset snapshots")
    parser.add_argument("--policy", help="JSON file with heldout_families and run rights grants")
    return parser


def dataset_main(*, context=None):
    args = dataset_parser().parse_args(sys.argv[2:])
    from sentilab_core import operations
    policy = json.loads(Path(args.policy).read_text()) if args.policy else None
    parameters = {"run_ids": args.run_ids}
    if args.output_dir is not None:
        parameters["output_dir"] = args.output_dir
    if policy is not None:
        parameters["policy"] = policy
    from sentilab_core.execution import admit
    from sentilab_mcp import sentilab_dataset_export
    admit("sentilab_dataset_export", parameters)
    context = context if context is not None else operations.environment_context()
    result = asyncio.run(sentilab_dataset_export(context, **parameters))
    print(json.dumps(result, allow_nan=False))


def chiplet_parser():
    parser = SafeParser(prog="sentilab chiplet")
    parser.add_argument("command", choices=cli_commands("chiplet"))
    parser.add_argument("--run-id")
    parser.add_argument("--fixture")
    parser.add_argument("--positions", type=json.loads)
    parser.add_argument("--cursor", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--policy", help="JSON file with heldout_families and run rights grants")
    return parser


def chiplet_main(*, context=None):
    args = vars(chiplet_parser().parse_args(sys.argv[2:]))
    command = args.pop("command")
    arguments = {key: value for key, value in args.items() if value is not None}
    if "policy" in arguments:
        arguments["policy"] = json.loads(Path(arguments["policy"]).read_text())
    from sentilab_core.execution import admit
    from sentilab_core.operations import environment_context
    from sentilab_mcp import TOOLS
    tool = "sentilab_chiplet_" + command
    admit(tool, arguments)
    context = context if context is not None else environment_context()
    result = asyncio.run(TOOLS[tool](context, **arguments))
    print(json.dumps(result, allow_nan=False))


def gb10_parser():
    parser = SafeParser(prog="sentilab gb10")
    parser.add_argument("command", choices=cli_commands("gb10"))
    parser.add_argument("--location", choices=["gb10", "pc", "both"])
    return parser


def gb10_main(*, context=None):
    args = gb10_parser().parse_args(sys.argv[2:])
    arguments = {"location": args.location} if args.location is not None else {}
    from sentilab_core.execution import admit
    from sentilab_core.operations import environment_context
    from sentilab_mcp import TOOLS
    tool = "sentilab_gb10_" + args.command.replace("-", "_")
    admit(tool, arguments)
    context = context if context is not None else environment_context()
    result = asyncio.run(TOOLS[tool](context, **arguments))
    print(json.dumps(result, allow_nan=False))


def research_parser():
    from sentilab_core import research

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            # argparse's default diagnostic includes caller-supplied text.
            print(research.dumps({"ok": False, "error": {"code": "invalid_input"}}))
            raise SystemExit(2)

    parser = Parser(prog="sentilab research")
    parser.add_argument("command", choices=cli_commands("research"))
    parser.add_argument("--ai-off", action="store_true")
    parser.add_argument("--namespace", required=True, help="JSON run_id/arm/family/seed/lab scope")
    parser.add_argument("--question")
    parser.add_argument("--request-id")
    return parser


def research_main(*, context=None):
    from sentilab_core import operations, research
    from sentilab_core.execution import authorize
    args = research_parser().parse_args(sys.argv[2:])
    authorize("sentilab_research_" + args.command)
    try:
        if len(args.namespace) > research.MAX_BYTES:
            raise ValueError()
        parameters = {"ai_off": args.ai_off, "namespace": json.loads(args.namespace)}
        if args.question is not None:
            parameters["question"] = args.question
        if args.request_id is not None:
            parameters["request_id"] = args.request_id
        context = context if context is not None else operations.environment_context()
        result = asyncio.run(dispatch("research_" + args.command, context, **parameters))
    except (ValueError, TypeError, OSError, RecursionError):
        result = {"ok": False, "error": {"code": "invalid_input"}}
    print(research.dumps(result))
    return 0 if result["ok"] else 2


def resultcheck_parser():
    parser = _ResultCheckParser(prog="sentilab resultcheck")
    parser.add_argument("--root", help="confine file reads to this directory (requires Linux procfs)")
    parser.add_argument("file", help="UTF-8 ResultCheck v2 JSON file")
    return parser


def build_parser(conductor=False):
    parser = SafeParser(prog="sentilab" if not conductor else "sentilab_core.conductor")
    if not conductor:
        parser.add_argument("namespace", choices=sorted({row.cli_command[0] for row in exposed()}),
                            help="use dataset --help for export options")
        parser.add_argument("command", choices=cli_commands("live"))
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
    return parser


def _main(conductor=False, *, context=None):
    check_cli_size(sys.argv[1:])
    if not conductor and sys.argv[1:2] in (["memory"], ["route"]):
        return advisory_main(context=context)
    if not conductor and sys.argv[1:2] == ["resultcheck"]:
        from sentilab_core.resultcheck import canonical, check_file, exit_code
        from sentilab_core.execution import authorize
        args = resultcheck_parser().parse_args(sys.argv[2:])
        authorize("sentilab_resultcheck")
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
        return research_main(context=context)
    if not conductor and sys.argv[1:2] == ["dataset"]:
        return dataset_main(context=context)
    if not conductor and sys.argv[1:2] == ["chiplet"]:
        return chiplet_main(context=context)
    if not conductor and sys.argv[1:2] == ["gb10"]:
        return gb10_main(context=context)
    parser = build_parser(conductor)
    args = parser.parse_args()
    from sentilab_core import operations
    from sentilab_core.budget import Limits
    command = "run" if conductor else args.command
    parameters = {"ai_off": args.ai_off}
    if command in ("run", "status", "verify") and args.run_id is not None:
        parameters["run_id"] = args.run_id
    if command == "run":
        parameters.update(duration=args.duration, interval=args.interval, renew=args.renew)
    from sentilab_core.execution import admit
    admit("sentilab_live_" + command, parameters)
    context = context if context is not None else operations.environment_context(ephemeral=args.ephemeral)
    context.options = {"fixture": args.fixture, "margin": args.margin, "grid": args.grid,
                       "deadline": args.deadline,
                       "limits": Limits(evals_per_hour=args.max_evals_per_hour, evals_per_run=args.max_evals_per_run),
                       **context.options}
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


def main(conductor=False, *, context=None):
    try:
        return _main(conductor, context=context)
    except PermissionError:
        print(json.dumps(error_receipt(-32001, "capability scope refused")))
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print(json.dumps(error_receipt(-32800, "request cancelled")))
        raise SystemExit(130) from None
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps(error_receipt(message=type(exc).__name__)))
        raise SystemExit(2) from None
    except Exception:
        print(json.dumps(error_receipt(-32603, "internal error")))
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
