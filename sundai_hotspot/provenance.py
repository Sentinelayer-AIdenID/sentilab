"""Evaluator build provenance and runtime library identity (SLAB-049). Nothing here runs an evaluator.

    python3 -m sundai_hotspot.provenance KIND [KIND ...]   after a build: write <binary>.provenance.json

A provenance file records what an evaluator binary is and how it was made: its SHA-256, the architecture, the
compiler, the make command and the Makefile's flag lines (HotSpot 6.0's CFLAGS always add -g, so the binary embeds
its build directory and its hash depends on that path), the installed SuperLU/BLAS/LAPACK/libc packages, and every
shared library the dynamic loader resolves for it, with content hashes and owning packages. validate-reference
refuses a binary whose provenance is missing or names other bytes, and refuses to run when the libraries it resolves
now differ from the ones its build resolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

SCHEMA = "sentilab-evaluator-build-provenance-v1"
# Compiled into HotSpot 7 when it is built with CI_ALLOCATION=1 (sundai_hotspot/ci_entry.h): such a binary runs only
# through sundai_hotspot.ci_gate under a CI reservation, so validate-reference refuses it.
CI_ENTRY_GUARD = b"CI HotSpot requires a reserved launch through ci_gate.run_hotspot"
PACKAGE_PATTERNS = ("libsuperlu*", "libblas*", "libopenblas*", "liblapack*", "libgfortran*", "libc6", "libgcc-s1",
                    "gcc", "gcc-[0-9]*")
_LDD_LINE = re.compile(r"^\s*(\S+)(?:\s+=>\s+(\S+))?\s+\(0x[0-9a-f]+\)\s*$")


class ProvenanceError(RuntimeError):
    """An evaluator's build provenance is missing, stale, or its runtime libraries changed."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(argv: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False,
                              env={"LANG": "C", "LC_ALL": "C", "PATH": os.defpath})
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolved_libraries(executable: Path) -> dict:
    """The shared objects the dynamic loader resolves for an executable, each with its real path and SHA-256.

    glibc's ldd asks the loader to map and list them; the program's own code does not run. A script or a static
    binary resolves none ("dynamic": false). Where ldd is unavailable the identity is unknown ("dynamic": null).
    """
    listing = _run(["ldd", str(executable)])
    if listing is None:
        return {"dynamic": None, "libraries": [], "note": "ldd is unavailable on this host"}
    if listing.returncode != 0:
        return {"dynamic": False, "libraries": [], "note": (listing.stdout + listing.stderr).strip()[:200]}
    libraries = []
    for line in listing.stdout.splitlines():
        match = _LDD_LINE.match(line)
        if not match:
            continue
        name, path = match.group(1), match.group(2)
        if path is None and name.startswith("/"):
            path = name
        if path is None:  # the kernel's vDSO has no file
            libraries.append({"name": name, "path": None, "realpath": None, "sha256": None})
            continue
        real = os.path.realpath(path)
        libraries.append({"name": name, "path": path, "realpath": real, "sha256": _sha256(Path(real))})
    return {"dynamic": True, "libraries": libraries}


def library_identity(resolved: dict) -> list[tuple]:
    """What must not change between build and run: each library's name, real path and content hash."""
    return [(item["name"], item["realpath"], item["sha256"]) for item in resolved.get("libraries", [])]


def _packages() -> dict[str, str]:
    listing = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${db:Status-Abbrev}\n", *PACKAGE_PATTERNS])
    if listing is None:
        return {}
    packages = {}
    for line in listing.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[1] and fields[2].startswith("ii"):
            packages[fields[0]] = fields[1]
    return packages


def _owner(path: str) -> str | None:
    listing = _run(["dpkg", "-S", path])
    if listing is None or listing.returncode != 0:
        return None
    return listing.stdout.split(":", 1)[0].strip() or None


def provenance_path(binary: Path) -> Path:
    return Path(binary).with_name(Path(binary).name + ".provenance.json")


def build_provenance(kind: str, binary: Path) -> dict:
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS
    binary = Path(binary).resolve()
    data = binary.read_bytes()
    makefile = binary.parent / "Makefile"
    flags = ([line.strip() for line in makefile.read_text(encoding="latin-1").splitlines()
              if re.match(r"\s*(CFLAGS|OFLAGS)\s*=", line)] if makefile.is_file() else [])
    compiler = _run(["gcc", "--version"])
    libraries = resolved_libraries(binary)
    for item in libraries["libraries"]:
        item["package"] = _owner(item["realpath"]) if item["realpath"] else None
    return {
        "schema": SCHEMA, "kind": kind, "binary": binary.as_posix(), "binary_sha256": hashlib.sha256(data).hexdigest(),
        "architecture": platform.machine(),
        "compiler": compiler.stdout.splitlines()[0] if compiler and compiler.stdout else None,
        "elf_comment_compilers": sorted({m.decode("ascii", "replace")
                                         for m in re.findall(rb"GCC: \([^)\x00]*\) [0-9][0-9.]*", data)}),
        "make": EVALUATOR_KINDS[kind]["make"],
        "makefile_flag_lines": flags,
        "debug_info": b".debug_info" in data,
        "ci_entry_guard": CI_ENTRY_GUARD in data,
        "build_dir": binary.parent.as_posix(),
        "build_dir_note": ("with -g the binary embeds its build directory, so its hash depends on that path; "
                           "every host pins its own binary through gate zero"),
        "packages": _packages(),
        "libraries": libraries,
    }


def require_build_provenance(kind: str, binary: Path, binary_sha256: str) -> dict:
    """The provenance of exactly these bytes, or a refusal."""
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS
    path = provenance_path(binary)
    if not path.is_file():
        raise ProvenanceError(f"{kind} has no build provenance at {path}; its build writes it "
                              f"({EVALUATOR_KINDS[kind]['build']})")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or data.get("kind") != kind or data.get("binary_sha256") != binary_sha256:
        raise ProvenanceError(f"{path} does not describe this {kind} binary ({binary_sha256[:12]}); rebuild it")
    return {"path": path.as_posix(), "sha256": _sha256(path), "provenance": data}


def main(argv: list[str] | None = None) -> int:
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS
    from sundai_hotspot.tap_oracle import REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kinds", nargs="+", choices=sorted(EVALUATOR_KINDS))
    args = parser.parse_args(argv)
    for kind in args.kinds:
        binary = REPO_ROOT / EVALUATOR_KINDS[kind]["binary"]
        record = build_provenance(kind, binary)
        provenance_path(binary).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        libraries = ", ".join(f"{item['name']}={item['sha256'][:12]}" for item in record["libraries"]["libraries"]
                              if item["sha256"])
        print(f"{kind}: {record['binary_sha256']} {record['architecture']} {record['compiler']}; {libraries}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
