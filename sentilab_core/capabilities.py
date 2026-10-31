"""CLI/MCP capability inventory, owned by the SLAB-043 conformance lane.

``done`` means the capability has both executable surfaces, not that its five
conformance checks have passed. Pending schemas reject all input until the lane
owner supplies an executable contract. No lane implementation belongs here.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Capability:
    name: str
    cli_command: tuple[str, ...]
    mcp_tool: str
    input_schema: dict
    output_schema: dict
    error_codes: tuple[int, ...]
    auth_scope: str
    stop_behaviour: str
    owner: str
    status: str = "done"
    pending_reason: str = ""


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def live_input(command):
    properties = {"ai_off": {"type": "boolean", "const": True}}
    required = ["ai_off"]
    if command != "stop":
        properties["run_id"] = {"type": "string"}
    if command == "verify":
        required.append("run_id")
    if command == "run":
        properties.update(duration={"type": "number", "minimum": 0, "maximum": 86400},
                          interval={"type": "number", "minimum": 0, "maximum": 3600},
                          renew={"type": "boolean"})
    return object_schema(properties, required)


DATASET_INPUT = object_schema({
    "run_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "output_dir": {"type": "string"},
    "policy": object_schema({
        "heldout_families": {"type": "array", "items": {"type": "string"}},
        "rights": {"type": "object", "additionalProperties": object_schema({
            "status": {"enum": ["ok", "blocked"]},
            "reason": {"type": "string", "minLength": 1}}, ["status", "reason"])}})},
    ["run_ids"])

# Responses retain their lane-owned fields and provenance. These schemas require
# the stable receipt fields without stripping additional lane evidence.
LIVE_OUTPUTS = {
    "run": {"type": "object", "required": ["run_id", "status", "seq", "head_hash",
                                              "projection", "board", "spend", "error"]},
    "status": {"oneOf": [{"type": "object", "required": ["runs", "stopped"]},
                          {"type": "object", "required": ["run_id", "ok", "prefix_end",
                                                           "head_hash", "projection", "board"]}]},
    "stop": {"type": "object", "properties": {"stopped": {"const": True}}, "required": ["stopped"]},
    "verify": {"type": "object", "required": ["run_id", "ok", "prefix_end", "head_hash",
                                                 "chain_error", "projection_error", "projection", "board"]},
}
ERROR_CODES = (-32602, -32603, -32800, -32000)


def pending(name, owner, reason):
    words = tuple(name.split("."))
    return Capability(name, words, "sentilab_" + "_".join(word.replace("-", "_") for word in words),
                      {"not": {}}, {"not": {}}, (), "pending owner contract",
                      "pending owner contract", owner, "pending", reason)


CAPABILITIES = tuple(
    Capability("live." + command, ("live", command), "sentilab_live_" + command,
               live_input(command), LIVE_OUTPUTS[command], ERROR_CODES,
               "local operator; AI off; injected signer" if command == "run" else "local operator; AI off",
               {"run": "STOP file halts conductor; MCP cancellation awaits cleanup",
                "status": "read remains available after STOP; synchronous handler",
                "stop": "writes STOP under admission lock; synchronous handler",
                "verify": "read remains available after STOP; synchronous handler"}[command],
               "PR #15 live lane")
    for command in ("run", "status", "stop", "verify")
) + (
    Capability("dataset.export", ("dataset", "export"), "sentilab_dataset_export", DATASET_INPUT,
               {"type": "object", "required": ["dataset_id", "directory", "schema", "sources",
                                                "policy", "counts", "sha256"]}, ERROR_CODES,
               "local operator; independently trusted ledger pins",
               "MCP cancellation reaps export worker; CLI export is synchronous", "PR #20 dataset lane"),
    pending("memory.recall", "PR #23 memory lane", "Owner module and transports absent from supplied snapshot"),
    pending("memory.snapshot", "PR #23 memory lane", "Owner module and transports absent from supplied snapshot"),
    pending("evidence.inspect", "PR #23 memory lane", "Owner module and transports absent from supplied snapshot"),
    pending("evidence.invalidate", "PR #23 memory lane", "Owner module and transports absent from supplied snapshot"),
    pending("resultcheck", "PR #21 ResultCheck lane", "Owner module and transports absent from supplied snapshot"),
    pending("lab.propose", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("lab.review", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("lab.repair", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("gb10.preflight-record", "SLAB-043 with SLAB-018 evidence owner", "Committed SLAB-018 evidence absent"),
    pending("gb10.status", "SLAB-043 with SLAB-018 evidence owner", "Committed SLAB-018 evidence absent"),
    pending("chiplet.build", "SLAB-043; existing controller/app lane", "Wrapper not implemented"),
    pending("chiplet.render", "SLAB-043; existing controller/app lane", "Wrapper not implemented"),
    pending("chiplet.replay", "SLAB-043; existing controller/app lane", "Wrapper not implemented"),
    pending("chiplet.export", "SLAB-043; existing controller/app lane", "Wrapper not implemented"),
)


def implemented():
    return tuple(row for row in CAPABILITIES if row.status == "done")


def for_tool(name):
    return next(row for row in CAPABILITIES if row.mcp_tool == name)


def cli_commands(namespace):
    return tuple(row.cli_command[1] for row in implemented()
                 if len(row.cli_command) == 2 and row.cli_command[0] == namespace)


def assert_surfaces(cli_commands, mcp_tools):
    """Compare actual parser leaves and advertised tool schemas with the registry.

    The caller must supply observations of the shipped surfaces, not sets built
    from this registry. Additions, omissions, duplicate tools and schema drift
    are all failures, including a pending capability accidentally exposed.
    """
    rows = implemented()
    expected_cli = {row.cli_command for row in rows}
    expected_mcp = {row.mcp_tool: row.input_schema for row in rows}
    observed_mcp = {tool["name"]: tool["inputSchema"] for tool in mcp_tools}
    if set(cli_commands) != expected_cli:
        raise ValueError("CLI capability registry drift")
    if len(observed_mcp) != len(mcp_tools) or observed_mcp != expected_mcp:
        raise ValueError("MCP capability registry drift")


def coverage_markdown():
    lines = ["# SLAB-043 capability coverage", "",
             "Generated by `python -m sentilab_core.capabilities --coverage`; do not edit the table.", "",
             "`done` records existing CLI/MCP entry points. It does **not** certify the five-check harness.",
             "Real-process tests cover unknown-input refusal without echoed values and the 64 KiB wire cap",
             "for every done row. The CLI cap counts UTF-8 argv bytes plus one separator per argument;",
             "the MCP cap counts frame bytes excluding the newline. Malformed MCP frames fail safely.",
             "Valid execution, scoped authorization, full schema validation and mid-call STOP remain unproved",
             "in this snapshot. Pending entries are reserved interfaces with rejecting schemas, not tools.", "",
             "| Capability | CLI | MCP | Status | Owner | Pending reason |",
             "|---|---|---|---|---|---|"]
    for row in CAPABILITIES:
        lines.append(f"| {row.name} | `sentilab {' '.join(row.cli_command)}` | `{row.mcp_tool}` | "
                     f"{row.status} | {row.owner} | {row.pending_reason or '—'} |")
    lines += ["", "Full schemas, current authorization requirements, errors and STOP behavior are in",
              "`sentilab_core/capabilities.py`; `python -m sentilab_core.capabilities` prints the inventory.", ""]
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", action="store_true", help="print the generated coverage document")
    parser.add_argument("--check", type=Path, help="check a generated coverage document without writing it")
    args = parser.parse_args()
    if args.check:
        if args.check.read_text(encoding="utf-8") != coverage_markdown():
            parser.error("coverage document differs from registry")
    elif args.coverage:
        print(coverage_markdown(), end="")
    else:
        print(json.dumps([asdict(row) for row in CAPABILITIES], indent=2))


if __name__ == "__main__":
    main()
