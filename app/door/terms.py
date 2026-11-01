"""The challenge terms the signed manifest pins, as the door serves them at GET /api/open/v1/door/terms.

A terms version names its text by hash: sentilab-open-terms/<n>@<sha256 of the text> (the contract's terms record).
The door serves the text of the manifest's highest accepted version (the version a JSON submission carries, and the
one the board names first), and only bytes whose SHA-256 is that version's pin. They are read once, when the door is
built, from DOOR_TERMS_DIR, default this tree's web/public/sentilab/open/terms (the API image carries it, see
.dockerignore), at the contract's canonical file name <n>@<sha256>.md. No manifest, no accepted version, or a file that
is absent, unreadable, larger than MAX_BYTES or of any other bytes: the door has no terms, and the route answers 503
terms_unavailable. It never serves another text, and never a lower version in place of the highest.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from open_proposals.contract.canonical import terms_path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "sentilab" / "open" / "terms"
VERSION = re.compile(r"sentilab-open-terms/([1-9][0-9]{0,5})@([0-9a-f]{64})")
MAX_BYTES = 65536


@dataclass(frozen=True)
class Terms:
    version: str
    sha256: str
    data: bytes


def pinned_version(manifest) -> str | None:
    """The highest-numbered well-formed version among the manifest's accepted terms (the first of equals), or None."""
    terms = manifest.get("terms") if isinstance(manifest, dict) else None
    versions = terms.get("accepted_versions") if isinstance(terms, dict) else None
    if not isinstance(versions, list):
        return None
    valid = [value for value in versions if isinstance(value, str) and VERSION.fullmatch(value)]
    return max(valid, key=lambda value: int(VERSION.fullmatch(value).group(1)), default=None)


def load(manifest, directory) -> Terms | None:
    """The pinned version's text from directory, or None unless its bytes hash to the version's pin."""
    version = pinned_version(manifest)
    if version is None:
        return None
    pin = VERSION.fullmatch(version).group(2)
    try:
        with (Path(directory) / PurePosixPath(terms_path(version)).name).open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except (OSError, ValueError):
        return None
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != pin:
        return None
    return Terms(version, pin, data)


def from_env(manifest, env) -> Terms | None:
    configured = env.get("DOOR_TERMS_DIR", "")
    return load(manifest, Path(configured) if configured else DEFAULT_DIR)
