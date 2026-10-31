"""Operator authentication for SLAB-049's gate-zero calls: a signed, hash-chained ledger and the operator's tags.

Two operator-owned facts make an admitted call authentic (warden #56967 and #57024; astra #57024 and #57025):

- **The signed ledger.** The operator's grant, every reservation and settlement, and every receipt are signed with
  the operator's Ed25519 key, whose PUBLIC key the manifest pins. The entries form a hash chain, and the grant
  binds the manifest, the call ids, the window, the CPU cap and the ledger's own directory. The private key stays
  with the operator supervisor; nothing here creates, reads from the repository or stores it.
- **The anchor.** A create-only tag namespace `gate0-<grant-id>/` in this repository, under its own ruleset (no
  update, no delete, no force-push, no bypass). The operator creates `reserve-<call-id>` before launch and
  `settle-<call-id>` after settlement. validate-reference creates `admit-<NN>`, the grant's admission chain, when it
  admits a call, and `launch-<call-id>` as its atomic launch claim. Each tag's commit message is JSON binding the
  grant, the manifest and the call (admit adds its place in the chain, the call's envelope and the running total;
  launch adds the signed reservation's hash; settle adds the terminal status, the receipt and output hashes and
  the CPU charged). A second create of any tag fails, so neither admission nor launch can repeat, even if a caller's
  ledger is deleted, truncated or copied elsewhere.

Three roles, kept apart (astra #57031; root's round-D review of PR #56):

- **Admission** (admit_and_reserve): one critical section for the grant, before any process work. Under the ledger's
  lock it re-reads the ledger, checks the window, reads the anchored admission chain, charges every admitted call
  its envelope (or its measured CPU, if larger), refuses unless this call still fits the cap, checks the window again
  after those remote reads, CREATES the next admission tag, checks the window once more when the create returns (a
  late create stays consumed and charged, and nothing runs), and appends the signed reservation. The create-only
  chain serializes the balance for the whole grant: two requests, on this host or any other, can never both take the
  same place in it.
- **Evidence verification** (TagReader): tags are read one at a time by exact name (`GET /git/ref/<ref>`, the GitHub
  client pattern of scripts/ci_admit.py), a fixed allowlist, so no prefix match, pagination or cache can turn an
  unrelated or missing ref into an accepted call. An authenticated 404 is a confirmed absence; any other API, auth
  or network failure is AnchorUnavailable (ERROR, retry later), which never counts as absent and never passes.
- **Physical launch admission** (claim_launch): immediately before launch, validate-reference atomically CREATES
  the launch tag. Only the request whose create succeeds launches. An existing ref refuses; an uncertain create
  (no response after sending) consumes the call, with no launch, until the operator reconciles it.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
import math
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
ADMIT = "admit"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_GRANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class AuthenticationError(RuntimeError):
    """A signature, chain link, grant or binding does not verify: the evidence is not the operator's."""


class AnchorAbsent(LookupError):
    """A tag confirmed absent: an authenticated 404 for its exact name."""


class AnchorUnavailable(RuntimeError):
    """The anchor could not be read (API, auth or network failure): ERROR, retry later. Never an absence."""


class CreateUncertain(AnchorUnavailable):
    """A create-only ref's create was sent and its outcome is unknown: it may exist."""


class RefExists(RuntimeError):
    """A create-only ref already exists (GitHub answers 422)."""


class AdmissionRefused(RuntimeError):
    """Not admitted, and nothing consumed: the window is closed, the call is not in the grant or not reserved by the
    operator, it is already in the ledger or the admission chain, the grant's cap would be passed, or another request
    took the same place in the chain."""


class AdmissionUncertain(RuntimeError):
    """Not admitted here, and nothing runs: the admission tag's create has an unknown outcome. If the tag exists the
    call is consumed and charged; the operator reconciles it."""


class ClaimRefused(RuntimeError):
    """No launch: the call's launch tag already exists, or its reserve tag is missing or does not bind it."""


class ClaimUncertain(RuntimeError):
    """No launch, and the call is CONSUMED: the claim's create may have happened. The operator reconciles it."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cpu(value) -> float | None:
    """A CPU figure from a record, or None when it is not a finite, non-negative number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


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


def _append_entry(directory: Path, key: Ed25519PrivateKey, ledger: dict, manifest_sha256: str, kind: str, call: str,
                  payload: dict) -> dict:
    """Sign and write the next entry of a ledger just verified under its lock."""
    seq = len(ledger["entries"])
    entry = sign(key, {"schema": ENTRY_SCHEMA, "seq": seq, "prev_sha256": ledger["head_sha256"], "kind": kind,
                       "manifest_sha256": manifest_sha256, "call": call, **payload})
    _write_once(_entry_path(directory, seq), entry)
    return entry


def append(root: Path, key: Ed25519PrivateKey, public_hex: str, manifest_sha256: str, kind: str, call: str,
           payload: dict) -> dict:
    """Append a call's settlement after re-verifying the whole chain, under the ledger's lock. A call is settled once,
    after its reservation. Reservations are written only by admit_and_reserve."""
    if kind != "settlement":
        raise ValueError(f"append writes settlements only, not {kind!r}: reservations are written by "
                         "admit_and_reserve")
    if public_key_hex(key) != public_hex:
        raise AuthenticationError("the signing key is not the pinned operator key")
    directory = ledger_dir(root, manifest_sha256)
    with _lock(directory):
        ledger = read_ledger(root, public_hex, manifest_sha256)
        if set(call_entries(ledger, call)) != {"reservation"}:
            raise AuthenticationError(f"{call} has no open reservation to settle")
        return _append_entry(directory, key, ledger, manifest_sha256, kind, call, payload)


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


def admit_ref(grant_id: str, seq: int) -> str:
    """The admission chain's place `seq` (admit-01, admit-02, ...)."""
    if (not _GRANT_ID.fullmatch(grant_id) or isinstance(seq, bool) or not isinstance(seq, int)
            or not 1 <= seq <= 99):
        raise ValueError("not an admission tag")
    return f"{TAG_NAMESPACE}{grant_id}/{ADMIT}-{seq:02d}"


def tag_message(kind: str, grant_id: str, manifest_sha256: str, call: str, *, receipt_sha256: str | None = None,
                outputs: dict | None = None, status: str | None = None, reservation_sha256: str | None = None,
                charged_cpu_s: float | None = None) -> str:
    """The exact commit message of a per-call tag (sorted keys, compact JSON). The operator writes reserve and settle
    (settle records the terminal status, the receipt and output hashes and the CPU charged; a failure is settled
    too); claim_launch writes launch, binding the signed reservation."""
    body = {"schema": TAG_SCHEMA, "kind": kind, "grant_id": grant_id, "manifest_sha256": manifest_sha256, "call": call}
    if kind == "launch":
        body.update(reservation_sha256=reservation_sha256)
    if kind == "settle":
        body.update(status=status, receipt_sha256=receipt_sha256, outputs=dict(outputs or {}),
                    charged_cpu_s=charged_cpu_s)
    return canonical(body).decode("ascii")


def admit_message(grant_id: str, manifest_sha256: str, seq: int, call: str, *, envelope_cpu_s: float,
                  total_cpu_s: float, previous_sha: str | None) -> str:
    """The commit message of the chain's place `seq`: the call admitted there, its envelope, the running total of
    envelopes, and the commit of the place before it."""
    return canonical({"schema": TAG_SCHEMA, "kind": ADMIT, "grant_id": grant_id, "manifest_sha256": manifest_sha256,
                      "seq": seq, "call": call, "envelope_cpu_s": envelope_cpu_s, "total_cpu_s": total_cpu_s,
                      "previous_sha": previous_sha}).decode("ascii")


class TagReader:
    """Reads one tag at a time by its exact name. `request(method, path)` returns parsed JSON, raises AnchorAbsent
    for an authenticated 404 of a ref and AnchorUnavailable for anything else that fails."""

    def __init__(self, request):
        self.request = request

    def _fetch(self, ref: str) -> tuple[dict, dict] | None:
        """The JSON message and the commit an exact ref points at; None when the ref is confirmed absent."""
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
        if not isinstance(message, dict) or message.get("schema") != TAG_SCHEMA:
            raise AuthenticationError(f"{ref} does not carry a gate-zero message")
        return message, commit

    def read(self, grant_id: str, kind: str, call: str, manifest_sha256: str) -> dict | None:
        """The tag's message, None when it is confirmed absent; AuthenticationError when it exists but does not bind
        this grant, manifest and call; AnchorUnavailable when it cannot be read."""
        found = self.resolve(grant_id, kind, call, manifest_sha256)
        return None if found is None else found[0]

    def resolve(self, grant_id: str, kind: str, call: str, manifest_sha256: str) -> tuple[dict, dict] | None:
        """read(), with the commit the tag points at."""
        ref = tag_ref(grant_id, kind, call)
        found = self._fetch(ref)
        if found is None:
            return None
        message, commit = found
        if (message.get("kind") != kind or message.get("grant_id") != grant_id
                or message.get("manifest_sha256") != manifest_sha256 or message.get("call") != call):
            raise AuthenticationError(f"{ref} binds another grant, manifest or call")
        receipt = message.get("receipt_sha256")
        if kind == "settle" and (not isinstance(message.get("status"), str)
                                 or not isinstance(message.get("outputs"), dict)
                                 or not (receipt is None or isinstance(receipt, str))
                                 or _cpu(message.get("charged_cpu_s")) is None):
            raise AuthenticationError(f"{ref} does not bind the terminal status, receipt and output hashes and the "
                                      "CPU charged")
        if kind == "launch" and not isinstance(message.get("reservation_sha256"), str):
            raise AuthenticationError(f"{ref} does not bind the signed reservation")
        return message, commit

    def admission(self, grant_id: str, seq: int, manifest_sha256: str) -> tuple[dict, dict] | None:
        """The admission chain's place `seq`, by its exact name: (message, commit), or None when confirmed absent."""
        ref = admit_ref(grant_id, seq)
        found = self._fetch(ref)
        if found is None:
            return None
        message = found[0]
        if (message.get("kind") != ADMIT or message.get("grant_id") != grant_id
                or message.get("manifest_sha256") != manifest_sha256 or message.get("seq") != seq):
            raise AuthenticationError(f"{ref} binds another grant, manifest or place")
        return found

    def admissions(self, grant: dict, manifest_sha256: str, envelopes: dict[str, float]) -> dict:
        """The grant's admission chain, read place by place (admit-01, admit-02, ...) up to its first confirmed
        absence. Every place must name a granted call not admitted before, at that call's own envelope, link the
        commit of the place before it and carry the running total; anything else is AuthenticationError."""
        grant_id, calls = grant["grant_id"], set(grant["calls"])
        entries, head, total = [], None, 0.0
        for seq in range(1, len(calls) + 2):
            found = self.admission(grant_id, seq, manifest_sha256)
            if found is None:
                return {"entries": entries, "total_cpu_s": total, "head_sha": head, "next_seq": seq}
            message, commit = found
            call, envelope = message.get("call"), _cpu(message.get("envelope_cpu_s"))
            recorded = _cpu(message.get("total_cpu_s"))
            if (call not in calls or call in {e["call"] for e in entries} or envelope is None
                    or envelope != float(envelopes.get(call, -1.0)) or message.get("previous_sha") != head
                    or recorded is None or abs(recorded - (total + envelope)) > 1e-9):
                raise AuthenticationError(f"{admit_ref(grant_id, seq)} breaks the grant's admission chain")
            entries.append({"seq": seq, "call": call, "envelope_cpu_s": envelope, "commit_sha": commit["sha"]})
            head, total = commit["sha"], recorded
        raise AuthenticationError("the admission chain is longer than the grant's calls")


def admission_charge(chain: dict, ledger: dict, tags: TagReader, grant_id: str, manifest_sha256: str) -> float:
    """What the grant has consumed: every admitted call at its envelope, or at its measured CPU when that is larger
    (this ledger's settlement, or the operator's settle tag from wherever it ran). Admitted work that failed, was
    refused after admission or never settled is charged in full, never reclaimed."""
    charged = 0.0
    for admitted in chain["entries"]:
        name = admitted["call"]
        figures = [admitted["envelope_cpu_s"]]
        settlement = call_entries(ledger, name).get("settlement")
        if settlement is not None and _cpu(settlement.get("charged_cpu_s")) is not None:
            figures.append(_cpu(settlement["charged_cpu_s"]))
        settle = tags.read(grant_id, "settle", name, manifest_sha256)
        if settle is not None:
            figures.append(_cpu(settle["charged_cpu_s"]))
        charged += max(figures)
    return charged


def _create_tag(request, ref: str, message: str, *, tree: str, parents: list[str]) -> str:
    """Create-only: a commit carrying the message, then the ref (POST /git/refs). Returns the commit's sha. Raises
    AnchorUnavailable when the commit is not confirmed (no ref create was sent), RefExists when the ref exists, and
    CreateUncertain when the ref create was sent and its outcome is unknown."""
    try:
        sha = request("POST", "/git/commits", {"message": message, "tree": tree, "parents": parents})["sha"]
    except (KeyError, TypeError) as exc:
        raise AnchorUnavailable(f"{ref}: the commit was not confirmed") from exc
    try:
        request("POST", "/git/refs", {"ref": "refs/" + ref, "sha": sha})
    except RefExists:
        raise
    except AnchorUnavailable as exc:
        raise CreateUncertain(f"{ref}: the create's outcome is unknown") from exc
    return sha


def admit_and_reserve(root: Path, key: Ed25519PrivateKey, public_hex: str, manifest_sha256: str, call: str,
                      payload: dict, *, request, envelopes: dict[str, float], not_after_utc: str | None = None,
                      now: datetime | None = None) -> dict:
    """THE ADMISSION, one critical section for the grant, before any process work (root, PR #56 round-D review):

    1. under the ledger's lock, re-read and verify the ledger, and check the call's place in the grant and that the
       ledger holds nothing for it;
    2. read the anchored admission chain; refuse a call admitted anywhere before;
    3. charge every admitted call its envelope or its measured CPU, whichever is larger (admission_charge), and
       refuse unless this call's envelope still fits the grant's cap;
    4. read the clock after every remote read, since those reads can cross the cutoff: outside the grant's window (or
       past the manifest's not_after_utc, when given) refuse, with nothing created and nothing consumed;
    5. CREATE the chain's next place, admit-<NN> (create-only: when another request took it first, this one is
       refused, never squeezed in);
    6. read the clock once more, after the CREATE returns: a create that returns after the cutoff stays consumed and
       charged, and its reservation records it as late, so validate-reference settles the call as window_closed
       before any process work;
    7. append the signed reservation, which binds that place.

    Nothing runs between the balance check and the reservation, and the chain makes the balance one for the whole
    grant: requests on two ledgers or two hosts cannot both read 490 and both admit 58.5 under a 600 cap. `now`
    fixes the clock (tests); otherwise every check reads the host clock afresh. The window bounds the admission of
    a new call only; a call admitted in time keeps running. Raises AdmissionRefused (nothing consumed),
    AdmissionUncertain (the admission tag may exist: nothing runs), AuthenticationError and AnchorUnavailable (no
    admission)."""
    if public_key_hex(key) != public_hex:
        raise AuthenticationError("the signing key is not the pinned operator key")
    clock = _now if now is None else (lambda: now)
    directory = ledger_dir(root, manifest_sha256)
    with _lock(directory):
        ledger = read_ledger(root, public_hex, manifest_sha256)
        grant = ledger["grant"]
        grant_id = grant["grant_id"]
        opens, closes = _utc(grant["not_before_utc"]), _utc(grant["not_after_utc"])
        if not_after_utc:
            closes = min(closes, _utc(not_after_utc))
        if call not in grant["calls"]:
            raise AdmissionRefused(f"{call} is not in the operator's grant")
        if call_entries(ledger, call):
            raise AdmissionRefused(f"{call} is already in the ledger: a call is admitted once and never retried")
        tags = TagReader(request)
        chain = tags.admissions(grant, manifest_sha256, envelopes)
        if call in {admitted["call"] for admitted in chain["entries"]}:
            raise AdmissionRefused(f"{call} is already admitted under grant {grant_id}: a call is admitted once")
        charged = admission_charge(chain, ledger, tags, grant_id, manifest_sha256)
        envelope = float(envelopes[call])
        if charged + envelope > float(grant["cpu_cap_s"]) + 1e-9:
            raise AdmissionRefused(f"{charged:.2f} CPU-s already charged plus this call's {envelope:g} would pass "
                                   f"the grant's {float(grant['cpu_cap_s']):g} CPU-s cap")
        reserve = tags.resolve(grant_id, "reserve", call, manifest_sha256)
        if reserve is None:
            raise AdmissionRefused(f"the operator has not reserved {call} (no reserve tag)")
        checked = clock()  # after every remote read (they can cross the cutoff) and before anything is created
        if not opens <= checked <= closes:
            raise AdmissionRefused(f"outside the window at admission ({checked.isoformat()}, read after the remote "
                                   "reads and before the admission tag): nothing created, nothing consumed. STOP")
        seq, total = chain["next_seq"], chain["total_cpu_s"] + envelope
        ref = admit_ref(grant_id, seq)
        message = admit_message(grant_id, manifest_sha256, seq, call, envelope_cpu_s=envelope, total_cpu_s=total,
                                previous_sha=chain["head_sha"])
        try:
            sha = _create_tag(request, ref, message, tree=reserve[1]["tree"]["sha"],
                              parents=[chain["head_sha"] or reserve[1]["sha"]])
        except RefExists as exc:
            raise AdmissionRefused(f"{ref} was taken by another request; nothing consumed, try again") from exc
        except CreateUncertain as exc:
            raise AdmissionUncertain(f"{ref}: the admission's outcome is unknown; nothing runs") from exc
        returned = clock()  # the create can return after the cutoff: the call is consumed, and nothing may run
        late = not opens <= returned <= closes
        admission = {"ref": ref, "seq": seq, "commit_sha": sha, "envelope_cpu_s": envelope, "total_cpu_s": total,
                     "charged_before_cpu_s": charged, "checked_utc": checked.isoformat(),
                     "created_utc": returned.isoformat(), "late": late}
        try:
            return _append_entry(directory, key, ledger, manifest_sha256, "reservation", call,
                                 {**payload, "admission": admission})
        except OSError as exc:  # admitted and charged in the chain, with no local record: nothing runs
            raise AdmissionUncertain(f"{ref} was created but the signed reservation could not be written: the call "
                                     "is consumed and charged; nothing runs") from exc


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
    message = tag_message("launch", grant_id, manifest_sha256, call, reservation_sha256=reservation_sha256)
    try:
        sha = _create_tag(request, launch_ref, message, tree=reserve[1]["tree"]["sha"], parents=[reserve[1]["sha"]])
    except RefExists as exc:
        raise ClaimRefused(f"{launch_ref} could not be created (it exists, or GitHub refused the create): "
                           "no launch") from exc
    except CreateUncertain as exc:
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
