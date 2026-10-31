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
    original_contract: str
    cli_command: tuple[str, ...]
    mcp_tool: str
    input_schema: dict
    output_schema: dict
    error_codes: tuple[int | str, ...]
    auth_scope: str
    stop_behaviour: str
    owner: str
    status: str = "done"
    pending_reason: str = ""
    kind: str = "capability"
    mapping_note: str = ""


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def live_input(command):
    properties = {"ai_off": {"type": "boolean", "const": True}}
    required = ["ai_off"]
    if command != "stop":
        properties["run_id"] = {"type": "string", "minLength": 1, "maxLength": 128}
    if command == "verify":
        required.append("run_id")
    if command == "run":
        properties.update(duration={"type": "number", "exclusiveMinimum": 0, "maximum": 86400},
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
ERROR_CODES = (-32602, -32603, -32800, -32000, -32001)

CHIPLET_INPUTS = {
    "build": object_schema({"fixture": {"const": "plate"},
                            "positions": {"type": "array", "minItems": 4, "maxItems": 4,
                                          "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                                    "items": {"type": "number"}}}}),
    "render": object_schema({"run_id": {"type": "string", "minLength": 1, "maxLength": 128},
                             "cursor": {"type": "integer", "minimum": 0, "maximum": 100000}}, ["run_id"]),
    "replay": object_schema({"run_id": {"type": "string", "minLength": 1, "maxLength": 128}}, ["run_id"]),
    "export": object_schema({"run_id": {"type": "string", "minLength": 1, "maxLength": 128},
                             "output_dir": {"type": "string"},
                             "policy": DATASET_INPUT["properties"]["policy"]}, ["run_id"]),
}
CHIPLET_OUTPUTS = {
    "build": {"type": "object", "required": ["fixture", "design", "design_hash", "scope"]},
    "render": {"type": "object", "required": ["run_id", "head_hash", "format", "view"]},
    "replay": LIVE_OUTPUTS["verify"],
    "export": {"type": "object", "required": ["dataset_id", "directory", "schema", "sources",
                                                 "policy", "counts", "sha256"]},
}


def pending(name, owner, reason, *, original_contract=None, kind="capability", mapping_note=""):
    words = tuple(name.split("."))
    return Capability(name, original_contract or name, words,
                      "sentilab_" + "_".join(word.replace("-", "_") for word in words),
                      {"not": {}}, {"not": {}}, (), "pending owner contract",
                      "pending owner contract", owner, "pending", reason, kind, mapping_note)


def research_input(command):
    scope = {key: {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"}
             for key in ("run_id", "arm", "family", "lab")}
    scope["seed"] = {"type": "integer", "minimum": 0, "maximum": 2147483647}
    field = "question" if command == "request" else "request_id"
    # Discovery stays dependency-free; the owner module enforces the byte bound.
    value = ({"type": "string", "minLength": 1, "maxLength": 8192}
             if field == "question" else {"type": "string", "pattern": "^[0-9a-f]{64}$"})
    return object_schema({"ai_off": {"const": True, "type": "boolean"},
                          "namespace": object_schema(scope, scope), field: value},
                         ["ai_off", "namespace", field])


CAPABILITIES = tuple(
    Capability("live." + command, "live." + command, ("live", command), "sentilab_live_" + command,
               live_input(command), LIVE_OUTPUTS[command], ERROR_CODES,
               "live." + command,
               {"run": "STOP file halts conductor; MCP cancellation awaits cleanup",
                "status": "read remains available after STOP; cancellation reaps worker",
                "stop": "writes STOP under admission lock; cancellation reaps worker",
                "verify": "read remains available after STOP; cancellation reaps worker"}[command],
               "PR #15 live lane")
    for command in ("run", "status", "stop", "verify")
) + (
    Capability("dataset.export", "dataset.export", ("dataset", "export"), "sentilab_dataset_export", DATASET_INPUT,
               {"type": "object", "required": ["dataset_id", "directory", "schema", "sources",
                                                "policy", "counts", "sha256"]}, ERROR_CODES,
               "dataset.export",
               "export remains available after STOP; cancellation reaps worker", "PR #20 dataset lane"),
    pending("memory.recall", "astra-slab006a-mesh", "PR #23 not merged into supplied main c40e6f1"),
    pending("memory.audit", "astra-slab006a-mesh", "PR #23 not merged; audit is not assumed to implement snapshot or evidence inspection"),
    pending("memory.route", "astra-slab006a-mesh", "PR #23 not merged; compile/evaluate mapping awaits the actual owner contract"),
    pending("memory.write", "astra-slab043-conformance over astra-slab006a-mesh", "Authorized write surface awaits the owner module and authorization contract"),
    pending("memory.invalidate", "astra-slab043-conformance over astra-slab006a-mesh", "Authorized invalidation surface awaits the owner module and authorization contract",
            original_contract="evidence.invalidate",
            mapping_note="Reserved memory spelling of SLAB-010 evidence.invalidate; no executable alias or coverage claimed"),
    pending("memory.snapshot", "astra-slab043-conformance over astra-slab006a-mesh", "Original SLAB-010 snapshot contract; PR #23 owner module not merged"),
    pending("evidence.inspect", "astra-slab043-conformance over astra-slab006a-mesh", "Original SLAB-010 evidence-inspection contract; PR #23 owner module not merged"),
    pending("evidence.invalidate", "astra-slab043-conformance over astra-slab006a-mesh", "Original SLAB-010 evidence-invalidation contract; PR #23 owner module not merged"),
    pending("intent.compile", "astra-slab043-conformance over SLAB-011 routing lane", "Original SLAB-011 contract; PR #23 route mapping must be checked against current main"),
    pending("route.evaluate", "astra-slab043-conformance over SLAB-011 routing lane", "Original SLAB-011 contract; PR #23 route mapping must be checked against current main"),
    Capability("resultcheck", "resultcheck", ("resultcheck",), "sentilab_resultcheck",
               object_schema({"file": {"type": "string"}}, ["file"]),
               {"type": "object", "required": ["status"]}, ERROR_CODES + ("file_unreadable",),
               "CLI local file authority; MCP host SENTILAB_RESULTCHECK_DIR confinement",
               "Read-only check; MCP cancellation kills and reaps its existing lane worker",
               "astra-slab043-conformance over PR #21", "pending_conformance",
               "Both surfaces exist on main; lane tests retained. Unified scope/STOP/five-check integration pending"),
    pending("lab.propose", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("lab.review", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("lab.repair", "PR #19 labs lane", "ReplayLab and Dispatcher exist; transport contract not registered"),
    pending("gb10.preflight-record", "astra-slab043-conformance", "SLAB-018 manifest and 67 payload hashes verified on c40e6f1; wrapper implementation pending",
            kind="evidence_reader", mapping_note="SLAB-043 recorded evidence only; does not implement train.preflight"),
    pending("gb10.status", "astra-slab043-conformance", "SLAB-018 manifest and 67 payload hashes verified on c40e6f1; wrapper implementation pending",
            kind="evidence_reader", mapping_note="SLAB-043 recorded evidence only; does not implement live device train.status"),
) + tuple(pending(name, "gpt-astra-carter (root)",
                  "Actual GB10 device/checkpoint/serve parity is pending with root; this CPU-only lane has no device access")
          for name in ("doctor", "train.preflight", "train.status", "train.start", "train.cancel",
                       "checkpoint.inspect", "checkpoint.select", "checkpoint.evaluate",
                       "checkpoint.promote", "checkpoint.serve", "checkpoint.rollback",
                       "route.doctor", "worker.probe")) + tuple(
          Capability("chiplet." + command, "chiplet." + command, ("chiplet", command), "sentilab_chiplet_" + command,
                     CHIPLET_INPUTS[command], CHIPLET_OUTPUTS[command], ERROR_CODES,
                     "chiplet." + command,
                     "read/fixture operation remains available after STOP; cancellation reaps worker",
                     "SLAB-043 over existing controller/ledger/browser/dataset lanes")
          for command in ("build", "render", "replay", "export")) + tuple(
    Capability("research." + command, "research." + command, ("research", command),
               "sentilab_research_" + command, research_input(command),
               {"type": "object", "required": ["ok"]},
               ERROR_CODES + ("invalid_input", "ai_off_required", "namespace_not_authorized", "stopped", "oversize"),
               "Host SENTILAB_RESEARCH_NAMESPACE; lane checks exact namespace and AI-off",
               "Request checks STOP before dispatch and after backend; status/export remain readable",
               "astra-slab043-conformance over PR #34", "pending_conformance",
               "Both surfaces exist on main; lane tests retained. Unified scope/STOP/five-check integration pending")
    for command in ("request", "status", "export"))


def implemented():
    return tuple(row for row in CAPABILITIES if row.status == "done")


def exposed():
    """All real surfaces, including lanes awaiting unified conformance proof."""
    return tuple(row for row in CAPABILITIES if row.status != "pending")


def for_tool(name):
    return next(row for row in CAPABILITIES if row.mcp_tool == name)


def cli_commands(namespace):
    return tuple(row.cli_command[1] for row in exposed()
                 if len(row.cli_command) == 2 and row.cli_command[0] == namespace)


def assert_surfaces(cli_commands, mcp_tools):
    """Compare actual parser leaves and advertised tool schemas with the registry.

    The caller must supply observations of the shipped surfaces, not sets built
    from this registry. Additions, omissions, duplicate tools and schema drift
    are all failures, including a pending capability accidentally exposed.
    """
    rows = exposed()
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
             "`pending_conformance` records merged public surfaces awaiting integration into the unified",
             "execution matrix. They are included in discovery/drift checks, with explicit owners and gaps.",
             "Real-process tests cover exact response bytes, output schemas, invalid input without echoed values,",
             "host-granted scopes and the 64 KiB wire cap for every done row. The run fixture is already STOPped",
             "before it starts and records zero solves; it does not prove active-run STOP parity.",
             "Eight recorded operations also exercise CLI SIGINT / MCP cancellation against real OS workers,",
             "asserting workers are reaped before acknowledgement and the MCP connection remains usable.",
             "This is request cancellation, not mid-call creation of a STOP file. That ticket check remains open.",
             "The CLI cap counts UTF-8 argv bytes plus one separator per argument;",
             "the MCP cap counts frame bytes excluding the newline. Malformed MCP frames fail safely.",
             "Pending entries are reserved interfaces with rejecting schemas, not tools.", "",
             "Original contract names are explicit. Reserved aliases do not mark their original contract done.",
             "PR #23 audit/route names are not assumed to cover snapshot, evidence inspection or intent compile.",
             "GB10 evidence readers are excluded from public-capability counts and cannot satisfy device parity.",
             "Device/checkpoint/serve rows retain the original SLAB-004/018/019/032/033/038 contract names",
             "from `docs/sentilab/draft-0.5/TICKETS.json` and remain pending with gpt-astra-carter (root).",
             "Chiplet entry points have the SLAB-043 fixture contract; they do not certify the broader",
             "SLAB-026 simulation/training contract or count private helper methods as capabilities.", "",
             "`SENTILAB_CAPABILITY_SCOPES` is a host-configured JSON array of exact capability names.",
             "Unset retains the local-operator trust boundary; an empty array denies all calls (-32001).",
             "Requests cannot grant themselves scopes. Existing AI-off and signer/pin checks still apply.",
             "CLI-only signer and solver configuration flags remain host options, not MCP arguments.", "",
             "Chiplet build validates the existing plate fixture; render returns the existing browser view model;",
             "replay verifies history; export calls the existing immutable dataset exporter. No solves occur.", "",
             "| Surface name | Original contract | Kind | CLI | MCP | Status | Owner | Pending reason / mapping |",
             "|---|---|---|---|---|---|---|---|"]
    for row in CAPABILITIES:
        notes = "; ".join(part for part in (row.pending_reason, row.mapping_note) if part) or "—"
        lines.append(f"| {row.name} | {row.original_contract} | {row.kind} | "
                     f"`sentilab {' '.join(row.cli_command)}` | `{row.mcp_tool}` | "
                     f"{row.status} | {row.owner} | {notes} |")
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
