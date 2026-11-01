#!/usr/bin/env python3
"""Fixed, text-only collaboration study runner (protocol v2)."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

PACKET_FILES = ("README.md", "config.json", "model.py", "results.json", "report.md")
FINDING_FIELDS = {"file", "location", "defect", "evidence"}


class InputError(ValueError):
    """Invalid study inputs; safe to report without file contents."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_packet(directory: Path) -> tuple[str, dict[str, str]]:
    if directory.is_symlink() or not directory.is_dir():
        raise InputError("packet must be a regular directory")
    if {path.name for path in directory.iterdir()} != set(PACKET_FILES):
        raise InputError("packet must contain exactly the five protocol files")
    sections, hashes = [], {}
    for name in PACKET_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise InputError("packet files must be regular files")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InputError("packet files must be UTF-8 text") from None
        hashes[name] = sha256(data)
        sections.append(f"### {name}\n{text}")
    return "\n\n".join(sections), hashes


def parse_final(text: str) -> dict | None:
    if not text.startswith("FINAL"):
        return None
    result = {"findings": [], "malformed": [], "discarded": 0}
    body = text[len("FINAL"):]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    for number, line in enumerate(body.splitlines(), start=1):
        try:
            finding = json.loads(line)
        except (ValueError, RecursionError):
            finding = None
        if not isinstance(finding, dict) or set(finding) != FINDING_FIELDS or not all(isinstance(v, str) for v in finding.values()):
            result["malformed"].append({"line": number, "text": line})
        elif len(result["findings"]) < 20:
            result["findings"].append(finding)
        else:
            result["discarded"] += 1
    return result


def claim_output(directory: Path) -> None:
    """Claim even an existing empty directory exclusively; never reuse a run."""
    if directory.is_symlink():
        raise InputError("output directory must be empty and not a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise InputError("output directory must start empty")
    try:
        with (directory / ".running").open("x", encoding="utf-8") as stream:
            stream.write("study-runner\n")
    except FileExistsError:
        raise InputError("output directory must start empty") from None


@dataclass(frozen=True)
class Inputs:
    protocol: dict
    prompts: dict[str, str]
    order: list[dict]
    packets: dict[str, str]
    packet_hashes: dict[str, dict[str, str]]
    freeze: dict


def read_json_bytes(data: bytes):
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise InputError("invalid JSON input") from None


def snapshot_inputs(protocol_path: Path, prompt_paths: dict[str, Path], order_path: Path, packets_root: Path) -> Inputs:
    """Read input bytes once so every job uses the same review packet."""
    protocol_bytes = protocol_path.read_bytes()
    order_bytes = order_path.read_bytes()
    prompt_bytes = {name: path.read_bytes() for name, path in prompt_paths.items()}
    try:
        prompts = {name: data.decode("utf-8") for name, data in prompt_bytes.items()}
    except UnicodeError:
        raise InputError("prompts must be UTF-8 text") from None
    protocol, order = read_json_bytes(protocol_bytes), read_json_bytes(order_bytes)
    if not isinstance(protocol, dict) or not isinstance(order, list):
        raise InputError("protocol must be an object and order must be a list")
    if packets_root.is_symlink() or not packets_root.is_dir():
        raise InputError("packets root must be a regular directory")
    packets, packet_hashes, tree = {}, {}, {}
    for directory in sorted(packets_root.iterdir()):
        message, hashes = read_packet(directory)
        packets[directory.name], packet_hashes[directory.name] = message, hashes
        tree.update({f"{directory.name}/{name}": digest for name, digest in hashes.items()})
    freeze = {
        "schema": "collab-study-freeze-v2",
        "runner_sha256": sha256(Path(__file__).read_bytes()),
        "protocol": protocol,
        "protocol_sha256": sha256(protocol_bytes),
        "prompts": {name: {"file": path.name, "sha256": sha256(prompt_bytes[name])} for name, path in prompt_paths.items()},
        "order_sha256": sha256(order_bytes),
        "packet_files": dict(sorted(tree.items())),
        "packets_tree_sha256": sha256(canonical(tree)),
    }
    return Inputs(protocol, prompts, order, packets, packet_hashes, freeze)


def verify_freeze(path: Path, actual: dict) -> None:
    if read_json_bytes(path.read_bytes()) != actual:
        raise InputError("freeze does not match current runner and inputs")


def validate_pilot(path: Path, sealed_hashes: list[dict[str, str]]) -> tuple[str, dict[str, str]]:
    message, hashes = read_packet(path)
    digest = sha256(canonical(hashes))
    if any(sha256(canonical(sealed)) == digest for sealed in sealed_hashes):
        raise InputError("pilot must differ from every sealed packet")
    return message, hashes
