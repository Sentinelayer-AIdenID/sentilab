"""Operator authentication for SLAB-049's gate-zero calls: a signed, hash-chained ledger and the operator's tags.

Two operator-owned facts make an admitted call authentic (warden #56967 and #57024; astra #57024 and #57025):

- **The signed ledger.** The operator's grant, every reservation and settlement, and every receipt are signed with
  the operator's Ed25519 key, whose PUBLIC key the manifest pins. The entries form a hash chain, and the grant
  binds the manifest, the call ids, the window, the CPU cap and the ledger's own directory. The private key stays
  with the operator supervisor; nothing here creates, reads from the repository or stores it.
- **The anchor.** A create-only tag namespace `gate0-<grant-id>/` in this repository, under its own ruleset (no
  update, no delete, no force-push, no bypass). The operator creates `reserve-<call-id>` before launch and
  `settle-<call-id>` after settlement; validate-reference creates `launch-<call-id>` as its atomic claim. Each
  tag's commit message is JSON binding the grant, the manifest and the call (launch adds the signed reservation's
  hash; settle adds the terminal status and the receipt and output hashes). A second create fails, so run-once holds
  even if a caller's ledger is deleted, truncated or copied elsewhere.

Two roles, kept apart (astra #57031):

- **Evidence verification** (TagReader): the gate reads reserve, launch and settle tags, each by its exact name
  (`GET /git/ref/<ref>`, the GitHub client pattern of scripts/ci_admit.py), a fixed allowlist, so no prefix match,
  pagination or cache can turn an unrelated or missing ref into an accepted call. An authenticated 404 is a
  confirmed absence; any other API, auth or network failure is AnchorUnavailable (ERROR, retry later), which never
  counts as absent and never passes.
- **Physical launch admission** (claim_launch): immediately before launch, validate-reference atomically CREATES
  the launch tag. Only the request whose create succeeds launches. An existing ref refuses; an uncertain create
  (no response after sending) consumes the call, with no launch, until the operator reconciles it.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ENTRY_SCHEMA = "sentilab-slab049-ledger-entry-v1"
GRANT_SCHEMA = "sentilab-slab049-grant-v1"
TAG_SCHEMA = "sentilab-slab049-gate0-tag-v1"
TAG_NAMESPACE = "tags/gate0-"
KINDS = ("grant", "reservation", "settlement")
TAG_KINDS = ("reserve", "launch", "settle")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_GRANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class AuthenticationError(RuntimeError):
    """A signature, chain link, grant or binding does not verify: the evidence is not the operator's."""


class AnchorAbsent(LookupError):
    """A tag confirmed absent: an authenticated 404 for its exact name."""


class AnchorUnavailable(RuntimeError):
    """The anchor could not be read (API, auth or network failure): ERROR, retry later. Never an absence."""


class RefExists(RuntimeError):
    """A create-only ref already exists (GitHub answers 422)."""


class ClaimRefused(RuntimeError):
    """No launch: the call's launch tag already exists, or its reserve tag is missing or does not bind it."""


class ClaimUncertain(RuntimeError):
    """No launch, and the call is CONSUMED: the claim's create may have happened. The operator reconciles it."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


# --------------------------------------------------------------------------------------------- keys and signatures


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """The operator's key, supplied at run time from outside the repository (an unencrypted PKCS8 PEM file)."""
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise AuthenticationError("the operator key must be an Ed25519 private key")
    return key


def public_key_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def sign(key: Ed25519PrivateKey, body: dict) -> dict:
    if "signature" in body:
        raise ValueError("a body to sign must not carry a signature")
    return {**body, "signature": key.sign(canonical(body)).hex()}


def verify(public_hex: str | None, signed: dict) -> dict:
    """The signed body without its signature, or AuthenticationError."""
    if not public_hex:
        raise AuthenticationError("no operator public key is pinned")
    if not isinstance(signed, dict) or not isinstance(signed.get("signature"), str):
        raise AuthenticationError("unsigned")
    body = {k: v for k, v in signed.items() if k != "signature"}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(signed["signature"]),
                                                                             canonical(body))
    except (InvalidSignature, ValueError) as exc:
        raise AuthenticationError("the signature does not verify with the pinned operator key") from exc
    return body


# --------------------------------------------------------------------------------------------- the signed ledger


def ledger_dir(root: Path, manifest_sha256: str) -> Path:
    """The ledger's place is derived from the manifest id under the operator's configured root, never from a
    record or a caller."""
    if not _HEX64.fullmatch(manifest_sha256 or ""):
        raise AuthenticationError("not a manifest id")
    return Path(root).resolve() / f"slab049-{manifest_sha256}"


def _entry_path(directory: Path, seq: int) -> Path:
    return directory / f"{seq:06d}.json"


def open_ledger(root: Path, key: Ed25519PrivateKey, manifest_sha256: str, *, grant_id: str, calls: list[str],
                not_before_utc: str, not_after_utc: str, cpu_cap_s: float) -> dict:
    """The operator's grant, as entry 0 of a new ledger. An operator tool: validate-reference never writes a grant."""
    if not _GRANT_ID.fullmatch(grant_id):
        raise ValueError("grant ids are 1-64 characters of letters, digits, '.', '_' and '-'")
    directory = ledger_dir(root, manifest_sha256)
    directory.mkdir(parents=True, exist_ok=False)
    grant = {"schema": GRANT_SCHEMA, "grant_id": grant_id, "manifest_sha256": manifest_sha256,
             "calls": sorted(set(calls)), "not_before_utc": not_before_utc, "not_after_utc": not_after_utc,
             "cpu_cap_s": float(cpu_cap_s), "ledger_dir": directory.as_posix()}
    entry = sign(key, {"schema": ENTRY_SCHEMA, "seq": 0, "prev_sha256": None, "kind": "grant",
                       "manifest_sha256": manifest_sha256, "call": None, "grant": grant})
    _write_once(_entry_path(directory, 0), entry)
    return entry


def read_ledger(root: Path, public_hex: str | None, manifest_sha256: str) -> dict:
    """Every entry, verified: contiguous sequence, operator signature, hash chain, one manifest, and a grant at 0
    that names this very directory (a copy elsewhere is refused)."""
    directory = ledger_dir(root, manifest_sha256)
    if not directory.is_dir():
        raise AuthenticationError(f"no ledger for manifest {manifest_sha256[:12]} under {Path(root).resolve()}")
    names = sorted(path.name for path in directory.iterdir() if path.name.endswith(".json"))
    if names != [_entry_path(directory, seq).name for seq in range(len(names))]:
        raise AuthenticationError("the ledger's entries are not one contiguous sequence")
    entries, previous = [], None
    for seq, name in enumerate(names):
        try:
            signed = json.loads((directory / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AuthenticationError(f"entry {seq} cannot be read") from exc
        body = verify(public_hex, signed)
        if (body.get("schema") != ENTRY_SCHEMA or body.get("seq") != seq or body.get("prev_sha256") != previous
                or body.get("manifest_sha256") != manifest_sha256 or body.get("kind") not in KINDS
                or (body["kind"] == "grant") != (seq == 0)):
            raise AuthenticationError(f"entry {seq} breaks the chain")
        entries.append(signed)
        previous = digest(signed)
    if not entries:
        raise AuthenticationError("no operator grant opens this ledger")
    grant = entries[0].get("grant")
    if (not isinstance(grant, dict) or grant.get("schema") != GRANT_SCHEMA
            or grant.get("manifest_sha256") != manifest_sha256 or grant.get("ledger_dir") != directory.as_posix()):
        raise AuthenticationError("the grant belongs to another manifest or another ledger directory")
    return {"dir": directory, "entries": entries, "grant": grant, "head_sha256": previous}


@contextlib.contextmanager
def _lock(directory: Path):
    import fcntl
    with open(directory / ".lock", "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_once(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(json.dumps(value, indent=1, sort_keys=True).encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "posix":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def append(root: Path, key: Ed25519PrivateKey, public_hex: str, manifest_sha256: str, kind: str, call: str,
           payload: dict) -> dict:
    """Append one signed entry after re-verifying the whole chain, under the ledger's lock. A call is reserved once
    and settled once, after its reservation; anything else is refused."""
    if kind not in ("reservation", "settlement"):
        raise ValueError(f"unknown entry kind {kind!r}")
    if public_key_hex(key) != public_hex:
        raise AuthenticationError("the signing key is not the pinned operator key")
    directory = ledger_dir(root, manifest_sha256)
    with _lock(directory):
        ledger = read_ledger(root, public_hex, manifest_sha256)
        existing = call_entries(ledger, call)
        if call not in ledger["grant"]["calls"]:
            raise AuthenticationError(f"{call} is not in the operator's grant")
        if kind == "reservation" and existing:
            raise AuthenticationError(f"{call} is already in the ledger: a call is reserved once and never retried")
        if kind == "settlement" and set(existing) != {"reservation"}:
            raise AuthenticationError(f"{call} has no open reservation to settle")
        seq = len(ledger["entries"])
        entry = sign(key, {"schema": ENTRY_SCHEMA, "seq": seq, "prev_sha256": ledger["head_sha256"], "kind": kind,
                           "manifest_sha256": manifest_sha256, "call": call, **payload})
        _write_once(_entry_path(directory, seq), entry)
    return entry


def call_entries(ledger: dict, call: str) -> dict[str, dict]:
    """The reservation and settlement of one call (either may be absent); a second of either is a broken ledger."""
    found = {}
    for entry in ledger["entries"][1:]:
        if entry["call"] == call:
            if entry["kind"] in found:
                raise AuthenticationError(f"{call} has two {entry['kind']} entries")
            found[entry["kind"]] = entry
    if "settlement" in found and "reservation" not in found:
        raise AuthenticationError(f"{call} settled without a reservation")
    return found


# --------------------------------------------------------------------------------------------- the operator's tags


def tag_ref(grant_id: str, kind: str, call: str) -> str:
    if kind not in TAG_KINDS or not _GRANT_ID.fullmatch(grant_id) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", call):
        raise ValueError("not a gate-zero tag")
    return f"{TAG_NAMESPACE}{grant_id}/{kind}-{call}"


def tag_message(kind: str, grant_id: str, manifest_sha256: str, call: str, *, receipt_sha256: str | None = None,
                outputs: dict | None = None, status: str | None = None, reservation_sha256: str | None = None) -> str:
    """The exact commit message of a tag (sorted keys, compact JSON). The operator writes reserve and settle (settle
    records the terminal status and the receipt and output hashes; a failure is settled too); claim_launch writes
    launch, binding the signed reservation."""
    body = {"schema": TAG_SCHEMA, "kind": kind, "grant_id": grant_id, "manifest_sha256": manifest_sha256, "call": call}
    if kind == "launch":
        body.update(reservation_sha256=reservation_sha256)
    if kind == "settle":
        body.update(status=status, receipt_sha256=receipt_sha256, outputs=dict(outputs or {}))
    return canonical(body).decode("ascii")


class TagReader:
    """Reads one tag at a time by its exact name. `request(method, path)` returns parsed JSON, raises AnchorAbsent
    for an authenticated 404 of a ref and AnchorUnavailable for anything else that fails."""

    def __init__(self, request):
        self.request = request

    def read(self, grant_id: str, kind: str, call: str, manifest_sha256: str) -> dict | None:
        """The tag's message, None when it is confirmed absent; AuthenticationError when it exists but does not bind
        this grant, manifest and call; AnchorUnavailable when it cannot be read."""
        found = self.resolve(grant_id, kind, call, manifest_sha256)
        return None if found is None else found[0]

    def resolve(self, grant_id: str, kind: str, call: str, manifest_sha256: str) -> tuple[dict, dict] | None:
        """read(), with the commit the tag points at."""
        ref = tag_ref(grant_id, kind, call)
        try:
            found = self.request("GET", "/git/ref/" + ref)
        except AnchorAbsent:
            return None
        try:
            if found["ref"] != "refs/" + ref or found["object"]["type"] != "commit":
                raise AuthenticationError(f"{ref} is not exactly this tag, or not a commit")
            commit = self.request("GET", "/git/commits/" + found["object"]["sha"])
            if commit["sha"] != found["object"]["sha"]:
                raise AuthenticationError(f"{ref}: the commit read is not the one the tag points at")
            message = json.loads(commit["message"])
        except AnchorAbsent as exc:
            raise AnchorUnavailable(f"{ref} points at a commit that cannot be read") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError(f"{ref} does not carry a readable JSON message") from exc
        if (not isinstance(message, dict) or message.get("schema") != TAG_SCHEMA or message.get("kind") != kind
                or message.get("grant_id") != grant_id or message.get("manifest_sha256") != manifest_sha256
                or message.get("call") != call):
            raise AuthenticationError(f"{ref} binds another grant, manifest or call")
        receipt = message.get("receipt_sha256")
        if kind == "settle" and (not isinstance(message.get("status"), str)
                                 or not isinstance(message.get("outputs"), dict)
                                 or not (receipt is None or isinstance(receipt, str))):
            raise AuthenticationError(f"{ref} does not bind the terminal status, receipt and output hashes")
        if kind == "launch" and not isinstance(message.get("reservation_sha256"), str):
            raise AuthenticationError(f"{ref} does not bind the signed reservation")
        return message, commit


def claim_launch(request, grant_id: str, manifest_sha256: str, call: str, *, reservation_sha256: str) -> dict:
    """Physical launch admission: atomically CREATE gate0-<grant>/launch-<call> immediately before launch.

    1. The reserve tag must exist, by its exact name, and bind this grant, manifest and call.
    2. A commit carrying the launch message is created on top of the reserve tag's commit.
    3. The launch ref is created (POST /git/refs, create-only). Only a successful create returns, so only it launches.

    Raises ClaimRefused when the launch ref already exists or no reserve tag binds the call (no launch),
    AnchorUnavailable when the reserve tag or the commit cannot be confirmed (no launch; no ref was created), and
    ClaimUncertain when the ref create's outcome is unknown after sending (no launch, and the call is consumed:
    it is never retried from the absence of a settle tag).
    """
    reserve_ref = tag_ref(grant_id, "reserve", call)
    launch_ref = tag_ref(grant_id, "launch", call)
    reserve = TagReader(request).resolve(grant_id, "reserve", call, manifest_sha256)
    if reserve is None:
        raise ClaimRefused(f"{reserve_ref} does not exist: the operator has not reserved this call")
    reserve_commit = reserve[1]
    message = tag_message("launch", grant_id, manifest_sha256, call, reservation_sha256=reservation_sha256)
    try:
        commit = request("POST", "/git/commits", {"message": message, "tree": reserve_commit["tree"]["sha"],
                                                   "parents": [reserve_commit["sha"]]})
        sha = commit["sha"]
    except (KeyError, TypeError) as exc:
        raise AnchorUnavailable(f"{launch_ref}: the claim's commit was not confirmed") from exc
    try:
        request("POST", "/git/refs", {"ref": "refs/" + launch_ref, "sha": sha})
    except RefExists as exc:
        raise ClaimRefused(f"{launch_ref} could not be created (it exists, or GitHub refused the create): "
                           "no launch") from exc
    except AnchorUnavailable as exc:
        raise ClaimUncertain(f"{launch_ref}: the create's outcome is unknown; the call is consumed") from exc
    return {"ref": launch_ref, "commit_sha": sha, "message": message}


def github_request(repository: str, credential: str):
    """The GitHub REST client of scripts/ci_admit.py (same endpoint, headers and timeout; credentials in memory only,
    never logged). A ref's 404 is a confirmed absence only when the same credential can read the repository itself
    (GitHub answers 404, not 403, to a credential without access); every other failure is AnchorUnavailable."""
    def send(method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            "https://api.github.com/repos/" + repository + path, method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + credential, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)

    def request(method: str, path: str, body: dict | None = None):
        try:
            return send(method, path, body)
        except urllib.error.HTTPError as exc:
            code = exc.code
        except (OSError, ValueError):
            raise AnchorUnavailable("GitHub anchor unavailable") from None
        if code == 404 and method == "GET" and path.startswith("/git/ref/"):
            try:
                visible = str((send("GET", "") or {}).get("full_name", "")).lower() == repository.lower()
            except (OSError, ValueError, AttributeError):  # HTTPError is an OSError
                visible = False
            if visible:
                raise AnchorAbsent(path)
            raise AnchorUnavailable("GitHub anchor: this credential cannot read the repository")
        if code == 422 and method == "POST" and path == "/git/refs":
            raise RefExists(path)
        raise AnchorUnavailable(f"GitHub anchor refused HTTP {code}")
    return request


def configured(manifest: dict, *, ledger_root: Path | None = None,
               tags: TagReader | None = None) -> tuple[Path, TagReader]:
    """The operator's ledger root and tag reader: explicit arguments, else SLAB049_LEDGER_ROOT and GH_TOKEN."""
    root = ledger_root or os.environ.get("SLAB049_LEDGER_ROOT")
    if not root:
        raise AuthenticationError("no operator ledger root is configured (SLAB049_LEDGER_ROOT)")
    if tags is None:
        credential = os.environ.get("GH_TOKEN")
        if not credential:
            raise AnchorUnavailable("no credential to read the operator's tags (GH_TOKEN)")
        tags = TagReader(github_request(manifest["anchor"]["repository"], credential))
    return Path(root), tags
