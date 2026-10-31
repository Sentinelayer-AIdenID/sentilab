"""Evaluator build provenance and runtime library identity (SLAB-049). Nothing here runs an evaluator.

    python3 -m sundai_hotspot.provenance KIND [KIND ...]   after a build: write <binary>.provenance.json

A provenance file records what an evaluator binary is and how it was made: its SHA-256, the architecture, the
compilers its ELF .comment section names, the make command and the Makefile's flag lines (HotSpot 6.0's CFLAGS always
add -g, so the binary embeds its build directory and its hash depends on that path), the installed SuperLU/BLAS/LAPACK/
libc packages, and every shared library the dynamic loader resolves for it, with content hashes and owning packages.
validate-reference refuses a binary whose provenance is missing or names other bytes, and refuses to run when the
libraries it resolves now differ from the ones its build resolved.

One process is started here: the binary's own dynamic loader listing its dependencies (what ldd runs), under
RLIMIT_CPU and a wall deadline. The compilers and the packages are read in-process (the ELF .comment section; dpkg's
status database and file lists), with no process. cpu_limited is the RLIMIT_CPU setting every SLAB-049 child process
uses.
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import struct
import subprocess
import sys

try:  # imported at module load: a child's preexec hook must never take the import lock
    import resource
except ImportError:  # Windows: no RLIMIT_CPU (validate-reference refuses there)
    resource = None

SCHEMA = "sentilab-evaluator-build-provenance-v1"
# Compiled into HotSpot 7 when it is built with CI_ALLOCATION=1 (sundai_hotspot/ci_entry.h): such a binary runs only
# through sundai_hotspot.ci_gate under a CI reservation, so validate-reference refuses it.
CI_ENTRY_GUARD = b"CI HotSpot requires a reserved launch through ci_gate.run_hotspot"
PACKAGE_PATTERNS = ("libsuperlu*", "libblas*", "libopenblas*", "liblapack*", "libgfortran*", "libc6", "libgcc-s1",
                    "gcc", "gcc-[0-9]*")
DPKG_ADMIN = Path("/var/lib/dpkg")
LOADER_CPU_LIMIT_S = 1   # RLIMIT_CPU on the loader's listing (it takes milliseconds)
LOADER_TIMEOUT_S = 10    # its wall deadline; its whole process group is killed there
_LDD_LINE = re.compile(r"^\s*(\S+)(?:\s+=>\s+(\S+))?\s+\(0x[0-9a-f]+\)\s*$")
_COMPILER = re.compile(rb"GCC: \([^)\x00]*\) [0-9][0-9.]*")
_PT_INTERP = 3


class ProvenanceError(RuntimeError):
    """An evaluator's build provenance is missing, stale, or its runtime libraries changed."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cpu_limited(seconds: int) -> dict:
    """subprocess keyword arguments that set RLIMIT_CPU in the child before exec, soft = hard (the kernel kills the
    process at the limit; its children inherit it). POSIX; an empty dict where there is no RLIMIT_CPU."""
    if resource is None:
        return {}

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    return {"preexec_fn": apply}


def elf_compilers(data: bytes) -> list[str]:
    """The compilers an ELF binary's .comment section names (GCC records one 'GCC: (...) x.y.z' per object)."""
    return sorted({match.decode("ascii", "replace") for match in _COMPILER.findall(data)})


def elf_interpreter(data: bytes) -> str | None:
    """The program interpreter (PT_INTERP) an ELF executable names: the dynamic loader the kernel starts for it at
    launch. None for a static ELF; ValueError for anything that is not ELF."""
    if data[:4] != b"\x7fELF" or data[4:5] not in (b"\x01", b"\x02") or data[5:6] not in (b"\x01", b"\x02"):
        raise ValueError("not an ELF file")
    order = "<" if data[5] == 1 else ">"
    # ELF64 or ELF32: the program header table's offset, entry size and count; each entry's p_offset and p_filesz.
    word, table, entry_offset, entry_size = ("Q", (32, 54), 8, 32) if data[4] == 2 else ("I", (28, 42), 4, 16)
    try:
        offset = struct.unpack_from(order + word, data, table[0])[0]
        size, count = struct.unpack_from(order + "HH", data, table[1])
        for index in range(count):
            header = offset + index * size
            if struct.unpack_from(order + "I", data, header)[0] == _PT_INTERP:
                start = struct.unpack_from(order + word, data, header + entry_offset)[0]
                length = struct.unpack_from(order + word, data, header + entry_size)[0]
                return data[start:start + length].rstrip(b"\x00").decode("utf-8")
    except (struct.error, UnicodeDecodeError) as exc:
        raise ValueError(f"a malformed ELF file: {exc}") from exc
    return None


def _loader_listing(loader: str, executable: Path) -> tuple[int | None, str]:
    """The loader's own listing of an executable's dependencies (LD_TRACE_LOADED_OBJECTS=1, which is what ldd runs):
    it maps them and prints where each resolved, and the program's code does not run. One process, in its own
    session, under RLIMIT_CPU and a wall deadline at which its whole group is killed."""
    process = subprocess.Popen([loader, str(executable)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env={"LD_TRACE_LOADED_OBJECTS": "1", "LANG": "C", "LC_ALL": "C"},
                               start_new_session=True, **cpu_limited(LOADER_CPU_LIMIT_S))
    try:
        output, _ = process.communicate(timeout=LOADER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)  # the leader is not reaped yet, so the group id is still its own
        process.communicate()
        return None, f"the loader passed its {LOADER_TIMEOUT_S} s deadline"
    return process.returncode, output.decode("utf-8", "replace")


def resolved_libraries(executable: Path) -> dict:
    """The shared objects the dynamic loader resolves for an executable, each with its real path and SHA-256.

    The loader is the one the executable names (PT_INTERP), the same one the kernel starts when it runs. A static
    binary resolves none ("dynamic": false). Where no listing can be made (not ELF, the loader cannot run or fails)
    the identity is unknown ("dynamic": null) and no library is listed.
    """
    try:
        loader = elf_interpreter(Path(executable).read_bytes())
    except ValueError as exc:
        return {"dynamic": None, "libraries": [], "note": f"no loader listing: {exc}"}
    if loader is None:
        return {"dynamic": False, "libraries": [], "note": "a static ELF names no program interpreter"}
    try:
        code, output = _loader_listing(loader, executable)
    except OSError as exc:
        return {"dynamic": None, "libraries": [], "loader": loader, "note": f"the loader cannot run: {exc.strerror}"}
    if code != 0:
        return {"dynamic": None, "libraries": [], "loader": loader, "note": output.strip()[:200]}
    libraries = []
    for line in output.splitlines():
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
    return {"dynamic": True, "loader": loader, "libraries": libraries}


def library_identity(resolved: dict) -> list[tuple]:
    """What must not change between build and run: each library's name, real path and content hash."""
    return [(item["name"], item["realpath"], item["sha256"]) for item in resolved.get("libraries", [])]


def _packages(admin: Path = DPKG_ADMIN) -> dict[str, str]:
    """Installed packages matching PACKAGE_PATTERNS, with versions, from dpkg's status database (what dpkg-query -W
    reports for them, read in-process). Empty where there is no dpkg database."""
    try:
        text = (admin / "status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    packages = {}
    for stanza in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines() if ": " in line and line[:1] not in " \t")
        name = fields.get("Package")
        if (name and fields.get("Version") and fields.get("Status") == "install ok installed"
                and any(fnmatch.fnmatchcase(name, pattern) for pattern in PACKAGE_PATTERNS)):
            packages[name] = fields["Version"]
    return packages


def _owners(paths: list[str], admin: Path = DPKG_ADMIN) -> dict[str, str]:
    """The package that installed each exact path, from dpkg's file lists (what dpkg -S reports, read in-process)."""
    wanted, owners = set(paths), {}
    for listing in sorted((admin / "info").glob("*.list")):
        try:
            lines = listing.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if line in wanted and line not in owners:
                owners[line] = listing.name[:-len(".list")].split(":", 1)[0]
    return owners


def provenance_path(binary: Path) -> Path:
    return Path(binary).with_name(Path(binary).name + ".provenance.json")


def build_provenance(kind: str, binary: Path) -> dict:
    from sundai_hotspot.gate_zero import EVALUATOR_KINDS
    binary = Path(binary).resolve()
    data = binary.read_bytes()
    makefile = binary.parent / "Makefile"
    flags = ([line.strip() for line in makefile.read_text(encoding="latin-1").splitlines()
              if re.match(r"\s*(CFLAGS|OFLAGS)\s*=", line)] if makefile.is_file() else [])
    compilers = elf_compilers(data)
    libraries = resolved_libraries(binary)
    owners = _owners([item["realpath"] for item in libraries["libraries"] if item["realpath"]])
    for item in libraries["libraries"]:
        item["package"] = owners.get(item["realpath"]) if item["realpath"] else None
    return {
        "schema": SCHEMA, "kind": kind, "binary": binary.as_posix(), "binary_sha256": hashlib.sha256(data).hexdigest(),
        "architecture": platform.machine(),
        "compiler": "; ".join(compilers) or None,
        "elf_comment_compilers": compilers,
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
