import argparse
import asyncio
import json
import sys
from pathlib import Path

from sentilab_core.capabilities import cli_commands, implemented
from sentilab_core.transport import check_cli_size, error_receipt


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid CLI arguments")


async def dispatch(command, context, **arguments):
    from sentilab_core import operations
    operation = getattr(operations, command)
    result = operation(context, **arguments)
    return await result if hasattr(result, "__await__") else result


def dataset_parser():
    parser = SafeParser(prog="sentilab dataset")
    parser.add_argument("command", choices=cli_commands("dataset"))
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--output-dir", help="parent of immutable dataset snapshots")
    parser.add_argument("--policy", help="JSON file with heldout_families and run rights grants")
    return parser


def dataset_main():
    args = dataset_parser().parse_args(sys.argv[2:])
    from sentilab_core import operations
    from sentilab_core.dataset import export
    context = operations.environment_context()
    policy = json.loads(Path(args.policy).read_text()) if args.policy else None
    result = export(context.root, args.run_ids, public_keys=context.public_keys,
                    output_dir=args.output_dir, policy=policy)
    print(json.dumps(result, allow_nan=False))


def build_parser(conductor=False):
    parser = SafeParser(prog="sentilab" if not conductor else "sentilab_core.conductor")
    if not conductor:
        parser.add_argument("namespace", choices=sorted({row.cli_command[0] for row in implemented()}),
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


def _main(conductor=False):
    check_cli_size(sys.argv[1:])
    if not conductor and sys.argv[1:2] == ["dataset"]:
        return dataset_main()
    parser = build_parser(conductor)
    args = parser.parse_args()
    from sentilab_core import operations
    from sentilab_core.budget import Limits
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


def main(conductor=False):
    try:
        return _main(conductor)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps(error_receipt(message=type(exc).__name__)))
        raise SystemExit(2) from None
    except Exception:
        print(json.dumps(error_receipt(-32603, "internal error")))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
