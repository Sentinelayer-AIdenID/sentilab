"""Fixed, stdlib-only GB10 observation program, also used for local file checks.

The backend sends this source over SSH stdin; it never installs or imports code
on GB10. No operation in this module starts a subprocess or writes a file.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import sys


PROBE_SCHEMA = "sentilab-gb10-readonly/1"
REMOTE_ROOT = "/home/dell/sentilab/preflight-20261031/attempt-01"
PC_ROOT = (
    "C:/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID/"
    ".sentinelayer/sentilab-planning/gpt-astra-carter/"
    "slab018-admission/attempt-01-artifacts"
)
# These pins come from SLAB018's committed original remote artifact manifest.
ARTIFACTS = (
    ("adapter/adapter_model.safetensors", 66126768,
     "695581e310def332bd6307527eff6546d95eebb88bec7e6f6ce288a5a61c0f80"),
    ("adapter/adapter_config.json", 1035,
     "ef6104b4d006baf86f90ddf1d0fc32a12a3951b70bfe3c2a0f06afcf5bdb413c"),
    ("execution-inputs.json", 2361,
     "230fd89ad116537c30cfd2c934d0ccae28dd4acec5d7b3361e1bd16bbecf1357"),
)
FILE_STATUSES = frozenset({"verified", "missing", "unsafe_path", "unreadable",
                           "size_mismatch", "hash_mismatch", "changed_during_read"})


class UnsafePath(ValueError):
    pass


def _identity_stat(info):
    return info.st_dev, info.st_ino, info.st_mode


def _content_stat(info):
    return (*_identity_stat(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _chain(path):
    """Do not resolve: a symlink or Windows reparse point must be refused."""
    if not path.is_absolute() or ".." in path.parts:
        raise UnsafePath()
    result = []
    current = Path(path.anchor)
    for part in (None, *path.parts[1:]):
        if part is not None:
            current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise UnsafePath()
        expected_type = stat.S_ISREG if current == path else stat.S_ISDIR
        if not expected_type(info.st_mode):
            raise UnsafePath()
        result.append(_identity_stat(info))
    return result


def _open_file(path, stack):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    if os.name == "posix":
        # Each component is opened relative to the pinned preceding directory.
        # An intermediate path swap cannot redirect an open to an arbitrary file.
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(path.anchor, directory_flags)
        stack.callback(os.close, parent)
        for part in path.parts[1:-1]:
            parent = os.open(part, directory_flags, dir_fd=parent)
            stack.callback(os.close, parent)
        descriptor = os.open(path.name, flags | os.O_NOFOLLOW, dir_fd=parent)
    else:
        descriptor = os.open(path, flags | getattr(os, "O_NOINHERIT", 0))
    stack.callback(os.close, descriptor)
    return descriptor


def verify_file(path, *, name, size, sha256):
    """Hash bounded bytes and report a point-in-time descriptor/path observation."""
    result = {"name": name, "status": "unreadable", "bytes": None, "sha256": None}
    try:
        path = Path(path)
        before_chain = _chain(path)
        with ExitStack() as stack:
            descriptor = _open_file(path, stack)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise UnsafePath()
            if before_chain != _chain(path) or before_chain[-1] != _identity_stat(before):
                result["status"] = "changed_during_read"
                return result
            result["bytes"] = before.st_size
            if before.st_size != size:
                result["status"] = "size_mismatch"
                return result
            digest = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    result["status"] = "changed_during_read"
                    return result
                digest.update(chunk)
                remaining -= len(chunk)
            extra = os.read(descriptor, 1)
            after = os.fstat(descriptor)
            if extra or _content_stat(before) != _content_stat(after) or before_chain != _chain(path):
                result["status"] = "changed_during_read"
                return result
            result["sha256"] = digest.hexdigest()
            result["status"] = "verified" if result["sha256"] == sha256 else "hash_mismatch"
    except FileNotFoundError:
        result["status"] = "missing"
    except (UnsafePath, ValueError):
        result["status"] = "unsafe_path"
    except OSError:
        result["status"] = "unreadable"
    return result


def checkpoint(root):
    return [verify_file(Path(root) / name, name=name, size=size, sha256=digest)
            for name, size, digest in ARTIFACTS]


def identity():
    import pwd  # The remote program is Linux-only; local file checks need no pwd.
    return {"hostname": platform.node(), "architecture": platform.machine(),
            "login": pwd.getpwuid(os.geteuid()).pw_name}


def _small_text(path):
    try:
        with Path(path).open("rb") as handle:
            value = handle.read(8193)
        return value.decode("ascii") if len(value) <= 8192 else ""
    except (OSError, UnicodeError):
        return ""


def device():
    driver = re.search(r"\b[0-9]{3}\.[0-9]{1,3}\.[0-9]{1,3}\b",
                       _small_text("/proc/driver/nvidia/version"))
    models = []
    try:
        with os.scandir("/proc/driver/nvidia/gpus") as entries:
            for index, entry in enumerate(entries):
                if index >= 8:
                    break
                if re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", entry.name):
                    found = re.search(r"^Model:\s*(NVIDIA GB10)\s*$",
                                      _small_text(Path(entry.path) / "information"), re.M)
                    if found:
                        models.append(found[1])
    except OSError:
        pass
    return {"python": platform.python_version(), "driver": driver[0] if driver else None,
            "gpu_model": "NVIDIA GB10" if models else None,
            "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")}


def probe(operation):
    result = {"schema": PROBE_SCHEMA, "operation": operation, "identity": identity()}
    if operation == "status":
        result["device"] = device()
    elif operation == "checkpoint":
        result["artifacts"] = checkpoint(REMOTE_ROOT)
    else:
        raise ValueError("unknown observation")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"status", "checkpoint"}:
        raise SystemExit(2)
    signal.alarm(12)
    try:
        print(json.dumps(probe(sys.argv[1]), allow_nan=False, separators=(",", ":")))
    except (OSError, ValueError, KeyError):
        # Never print file contents, raw OS errors or private diagnostic paths.
        raise SystemExit(2)
