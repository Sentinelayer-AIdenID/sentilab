"""age v1 (X25519) tooling for sealed notes (OP-F1; DESIGN.md section 3.7): Bech32 keys, the strict ASCII armour,
sealed-note parsing, a reference opener for tests, and sealing for vector generation.

A sealed note is the line "sentilab-open-sealed/1 <manifest_id> <key_version>", a LF, then the ASCII armour of an
age v1 file encrypted to the manifest's X25519 recipient. The plaintext is at most 4,096 bytes; the note at most 8,192.

- Test identities derive from public phrases at run time: the X25519 scalar is sha256(UTF-8 phrase). Nothing here
  stores key material; secret_key_string() exists only to hand a test identity to pyrage, in memory.
- reference_decrypt() is a minimal X25519-only age v1 opener on `cryptography`, written from the age specification
  (https://github.com/C2SP/C2SP/blob/main/age.md). It is a test reference, not the production opener: it lets CI open
  the vectors offline with no age implementation installed.
- seal() needs pyrage or the age binary, and is for generating vectors only.

Standard library and `cryptography` only; pyrage and the age binary are optional, and only seal() and sealer() use them.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import shutil
import subprocess
from importlib import metadata

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NOTE_SCHEMA = "sentilab-open-sealed/1"
PLAINTEXT_MAX_BYTES = 4096
NOTE_MAX_BYTES = 8192
ARMOR_BEGIN = "-----BEGIN AGE ENCRYPTED FILE-----"
ARMOR_END = "-----END AGE ENCRYPTED FILE-----"
ARMOR_COLUMNS = 64
AGE_INTRO = b"age-encryption.org/v1\n"
RECIPIENT_HRP = "age"
SECRET_HRP = "age-secret-key-"      # age prints identities upper-cased; the Bech32 checksum uses the lowercase form
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

_BECH32_VALUES = {char: value for value, char in enumerate(BECH32_CHARSET)}
_BECH32_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_NOTE_FIRST_LINE = re.compile(r"sentilab-open-sealed/1 ([0-9a-f]{64}) ([1-9][0-9]{0,5})\n")
_MANIFEST_ID = re.compile(r"[0-9a-f]{64}")
_UNPADDED_BASE64 = re.compile(rb"[A-Za-z0-9+/]*")
_X25519_INFO = b"age-encryption.org/v1/X25519"
_CHUNK_BYTES = 64 * 1024
_TAG_BYTES = 16
_NONCE_BYTES = 16


# ── Bech32: BIP-173 without its length limit, as age uses it ───────────────────────────────────────────────────

def _polymod(values) -> int:
    check = 1
    for value in values:
        top = check >> 25
        check = ((check & 0x1FFFFFF) << 5) ^ value
        for bit, generator in enumerate(_BECH32_GENERATOR):
            if (top >> bit) & 1:
                check ^= generator
    return check


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _convert_bits(values, source: int, target: int, pad: bool) -> list[int]:
    accumulator, bits, out = 0, 0, []
    mask, window = (1 << target) - 1, (1 << (source + target - 1)) - 1
    for value in values:
        if value >> source:
            raise ValueError("bech32: value out of range")
        accumulator = ((accumulator << source) | value) & window
        bits += source
        while bits >= target:
            bits -= target
            out.append((accumulator >> bits) & mask)
    if pad and bits:
        out.append((accumulator << (target - bits)) & mask)
    elif not pad and (bits >= source or (accumulator << (target - bits)) & mask):
        raise ValueError("bech32: excess or non-zero padding bits")
    return out


def bech32_encode(hrp: str, data: bytes) -> str:
    """Bech32 of `data` under a lowercase human-readable part (BIP-173 encoders emit lowercase; upper-case after)."""
    if not hrp or hrp != hrp.lower() or any(not 33 <= ord(char) <= 126 for char in hrp):
        raise ValueError("bech32: the human-readable part is one or more lowercase characters in 33-126")
    values = _convert_bits(bytes(data), 8, 5, True)
    polymod = _polymod(_hrp_expand(hrp) + values + [0] * 6) ^ 1
    checksum = [(polymod >> (5 * (5 - index))) & 31 for index in range(6)]
    return hrp + "1" + "".join(BECH32_CHARSET[value] for value in values + checksum)


def bech32_decode(text: str) -> tuple[str, bytes]:
    """(the human-readable part in lowercase, the data) of a Bech32 string. Characters outside 33-126, mixed case, a
    missing or misplaced separator, an invalid data character, a bad checksum or bad padding bits raise ValueError."""
    if not isinstance(text, str) or any(not 33 <= ord(char) <= 126 for char in text):
        raise ValueError("bech32: characters outside 33-126")
    if text != text.lower() and text != text.upper():
        raise ValueError("bech32: mixed case")
    text = text.lower()
    separator = text.rfind("1")
    if separator < 1 or separator + 7 > len(text):
        raise ValueError("bech32: the separator is missing or misplaced")
    hrp, data = text[:separator], text[separator + 1:]
    if any(char not in _BECH32_VALUES for char in data):
        raise ValueError("bech32: invalid data character")
    values = [_BECH32_VALUES[char] for char in data]
    if _polymod(_hrp_expand(hrp) + values) != 1:
        raise ValueError("bech32: invalid checksum")
    return hrp, bytes(_convert_bits(values[:-6], 5, 8, False))


# ── keys ───────────────────────────────────────────────────────────────────────────────────────────────────────

def identity_from_phrase(phrase: str) -> tuple[bytes, str]:
    """A test identity from a public phrase: (the X25519 scalar sha256(UTF-8 phrase), its age1... recipient)."""
    scalar = hashlib.sha256(phrase.encode("utf-8")).digest()
    return scalar, recipient_from_scalar(scalar)


def recipient_from_scalar(scalar: bytes) -> str:
    """The age recipient of an X25519 identity: Bech32, human-readable part "age", of X25519(scalar, basepoint)."""
    public = X25519PrivateKey.from_private_bytes(bytes(scalar)).public_key().public_bytes_raw()
    return bech32_encode(RECIPIENT_HRP, public)


def secret_key_string(scalar: bytes) -> str:
    """age's text form of an X25519 identity (Bech32 under "age-secret-key-", upper-cased), built in memory only to
    hand a test identity to pyrage. Never write it to a file, a log or any output."""
    if not isinstance(scalar, (bytes, bytearray)) or len(scalar) != 32:
        raise ValueError("an X25519 identity is 32 bytes")
    return bech32_encode(SECRET_HRP, bytes(scalar)).upper()


# ── ASCII armour ───────────────────────────────────────────────────────────────────────────────────────────────

def _ascii(value, what: str) -> str:
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("ascii")        # UnicodeDecodeError is a ValueError
    if not isinstance(value, str) or not value.isascii():
        raise ValueError(f"{what}: expected ASCII text")
    return value


def armor(data: bytes) -> str:
    """The ASCII armour of an age file: the BEGIN line, padded standard base64 in 64-column lines (the last one 4 to
    64 columns), then the END line, each line ending in LF. The same bytes as age's armour (rage's on Windows ends
    its lines in CRLF instead)."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("armour: expected a non-empty age file")
    encoded = base64.b64encode(bytes(data)).decode("ascii")
    lines = [encoded[start:start + ARMOR_COLUMNS] for start in range(0, len(encoded), ARMOR_COLUMNS)]
    return "\n".join([ARMOR_BEGIN, *lines, ARMOR_END]) + "\n"


def dearmor(text) -> bytes:
    """The age file inside a strict armour: exactly armor()'s output, optionally without its final LF (a shell's
    "$(cat sealed.txt)" drops it). Anything else raises ValueError: other markers or line widths, a short line before
    the last, missing or extra padding, non-zero padding bits, another alphabet, CR, blank lines, an empty body, or
    any text before BEGIN or after END."""
    lines = _ascii(text, "armour").split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) < 3 or lines[0] != ARMOR_BEGIN or lines[-1] != ARMOR_END:
        raise ValueError("armour: a missing or altered BEGIN or END line, or no body")
    try:
        data = base64.b64decode("".join(lines[1:-1]), validate=True)
    except binascii.Error:
        raise ValueError("armour: not padded standard base64") from None
    if not data or armor(data) != "\n".join(lines) + "\n":
        raise ValueError("armour: not the canonical encoding (line widths, padding or padding bits)")
    return data


# ── sealed notes ───────────────────────────────────────────────────────────────────────────────────────────────

def parse_note(note) -> tuple[str, int, bytes]:
    """(manifest_id, key_version, the binary age file) of a sealed note; anything else raises ValueError. The note is
    at most 8,192 bytes, and its first line is exactly "sentilab-open-sealed/1", a space, 64 lowercase hex characters,
    a space and a positive integer without leading zeros, then LF; dearmor() takes the rest."""
    text = _ascii(note, "sealed note")
    if len(text) > NOTE_MAX_BYTES:
        raise ValueError("sealed note: over 8,192 bytes")
    match = _NOTE_FIRST_LINE.match(text)
    if match is None:
        raise ValueError("sealed note: the first line is not 'sentilab-open-sealed/1 <manifest_id> <key_version>'")
    return match.group(1), int(match.group(2)), dearmor(text[match.end():])


# ── the reference opener (tests only) ──────────────────────────────────────────────────────────────────────────

def reference_decrypt(age_file: bytes, scalar: bytes) -> bytes:
    """The plaintext of a binary age v1 file for one X25519 identity (its 32-byte scalar). Any failure raises
    ValueError. A test reference opener, not production code.

    Following age.md: the version line; one or more stanzas, each "-> " and space-separated VCHAR arguments, then a
    canonical unpadded base64 body in 64-column lines that ends with a shorter, possibly empty, line. Unrecognised
    stanzas are ignored; an X25519 stanza must have exactly one argument after its type, a canonical 32-byte share,
    and a 32-byte body, and an all-zero shared secret aborts. Then "--- " and the HMAC-SHA-256 of the header up to and
    including "---", keyed by HKDF-SHA-256(file key, empty salt, "header"); a 16-byte nonce; and 64 KiB
    ChaCha20-Poly1305 STREAM chunks under HKDF-SHA-256(file key, nonce, "payload"), each nonce an 11-byte big-endian
    counter and a final-chunk flag. The final chunk may be short, and is empty only when the whole payload is."""
    if not isinstance(age_file, (bytes, bytearray)) or not isinstance(scalar, (bytes, bytearray)) or len(scalar) != 32:
        raise ValueError("age: expected the binary age file and a 32-byte X25519 identity")
    stanzas, header, mac, payload = _parse_header(bytes(age_file))
    file_key = _unwrap(stanzas, bytes(scalar))
    verifier = hmac.HMAC(_hkdf(file_key, b"", b"header"), hashes.SHA256())
    verifier.update(header)
    try:
        verifier.verify(mac)
    except InvalidSignature:
        raise ValueError("age: bad header MAC") from None
    if len(payload) < _NONCE_BYTES:
        raise ValueError("age: truncated payload")
    return _open_stream(_hkdf(file_key, payload[:_NONCE_BYTES], b"payload"), payload[_NONCE_BYTES:])


def _hkdf(key_material: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(key_material)


def _unpadded_base64(text: bytes) -> bytes:
    """Canonical standard base64 without padding, the age header's encoding; anything else raises ValueError."""
    if not _UNPADDED_BASE64.fullmatch(text) or len(text) % 4 == 1:
        raise ValueError("age: header base64 is not canonical unpadded base64")
    data = base64.b64decode(text + b"=" * (-len(text) % 4))
    if base64.b64encode(data).rstrip(b"=") != text:
        raise ValueError("age: header base64 is not canonical unpadded base64")
    return data


def _line(data: bytes, start: int) -> tuple[bytes, int]:
    end = data.find(b"\n", start)
    if end < 0:
        raise ValueError("age: truncated header")
    return data[start:end], end + 1


def _parse_header(data: bytes):
    """(stanzas as (arguments, body), the header bytes the MAC covers, the MAC, the payload)."""
    if not data.startswith(AGE_INTRO):
        raise ValueError("age: not an age-encryption.org/v1 file")
    position, stanzas = len(AGE_INTRO), []
    while True:
        line, following = _line(data, position)
        if line.startswith(b"---"):
            if not stanzas or not line.startswith(b"--- "):
                raise ValueError("age: malformed header end")
            mac = _unpadded_base64(line[4:])
            if len(mac) != 32:
                raise ValueError("age: the header MAC is not 32 bytes")
            return stanzas, data[:position + 3], mac, data[following:]
        if not line.startswith(b"-> "):
            raise ValueError("age: unexpected header line")
        arguments = line[3:].split(b" ")
        if any(not argument or min(argument) < 0x21 or max(argument) > 0x7E for argument in arguments):
            raise ValueError("age: malformed stanza arguments")
        body = bytearray()
        while True:
            line, following = _line(data, following)
            if len(line) > ARMOR_COLUMNS:
                raise ValueError("age: stanza body line over 64 columns")
            body += _unpadded_base64(line)
            if len(line) < ARMOR_COLUMNS:
                break
        stanzas.append((arguments, bytes(body)))
        position = following


def _unwrap(stanzas, scalar: bytes) -> bytes:
    """The file key from the first X25519 stanza addressed to this identity."""
    identity = X25519PrivateKey.from_private_bytes(scalar)
    ours = identity.public_key().public_bytes_raw()
    for arguments, body in stanzas:
        if arguments[0] != b"X25519":
            continue                                    # age.md: identities ignore unrecognised stanzas
        if len(arguments) != 2:
            raise ValueError("age: an X25519 stanza has exactly one argument after its type")
        share = _unpadded_base64(arguments[1])
        if len(share) != 32 or len(body) != 32:
            raise ValueError("age: malformed X25519 stanza (share or body not 32 bytes)")
        try:
            shared = identity.exchange(X25519PublicKey.from_public_bytes(share))
        except ValueError:
            raise ValueError("age: low-order X25519 share") from None
        if shared == bytes(32):
            raise ValueError("age: all-zero X25519 shared secret")
        try:
            return ChaCha20Poly1305(_hkdf(shared, share + ours, _X25519_INFO)).decrypt(bytes(12), body, None)
        except InvalidTag:
            continue                                    # addressed to another identity
    raise ValueError("age: no X25519 stanza opens with this identity")


def _open_stream(key: bytes, data: bytes) -> bytes:
    aead, chunks, counter, position = ChaCha20Poly1305(key), [], 0, 0
    while True:
        remaining = len(data) - position
        final = remaining <= _CHUNK_BYTES + _TAG_BYTES
        if remaining < _TAG_BYTES or (final and remaining == _TAG_BYTES and counter):
            raise ValueError("age: truncated payload, or an empty final chunk after a full one")
        size = remaining if final else _CHUNK_BYTES + _TAG_BYTES
        nonce = counter.to_bytes(11, "big") + bytes((1 if final else 0,))
        try:
            chunks.append(aead.decrypt(nonce, data[position:position + size], None))
        except InvalidTag:
            raise ValueError("age: a payload chunk failed authentication") from None
        if final:
            return b"".join(chunks)
        position, counter = position + size, counter + 1


# ── sealing: vector generation only (pyrage or the age binary) ─────────────────────────────────────────────────

def _implementation():
    """("pyrage", the module) when pyrage imports, else ("age", its path) for an age binary on PATH."""
    try:
        import pyrage
    except ImportError:
        path = shutil.which("age")
        if path is None:
            raise RuntimeError("sealing needs pyrage or the age binary, and neither is available") from None
        return "age", path
    return "pyrage", pyrage


def sealer() -> dict:
    """The implementation seal() uses here and its version, to record with generated vectors."""
    name, implementation = _implementation()
    if name == "age":
        result = subprocess.run([implementation, "--version"], capture_output=True, text=True, check=True)
        return {"implementation": "age", "version": result.stdout.strip()}
    info = {"implementation": "pyrage", "version": metadata.version("pyrage")}
    direct = json.loads(metadata.distribution("pyrage").read_text("direct_url.json") or "{}")
    wheel_sha256 = direct.get("archive_info", {}).get("hashes", {}).get("sha256")
    if wheel_sha256:        # pip records the archive hash it verified when installing from a file or URL with a hash
        info.update(wheel=direct.get("url", "").rsplit("/", 1)[-1], wheel_sha256=wheel_sha256)
    return info


def seal(plaintext: bytes, manifest_id: str, key_version: int, recipient: str) -> str:
    """A sealed note: the first line naming `manifest_id` and `key_version`, then the armour of an age v1 file that
    pyrage (or the age binary) encrypts to `recipient`. Generation only, and it needs no secret key. The first line
    names `key_version` as given even when `recipient` belongs to another version, which the mismatch vector uses."""
    if not isinstance(plaintext, (bytes, bytearray)) or len(plaintext) > PLAINTEXT_MAX_BYTES:
        raise ValueError("seal: the plaintext is bytes, at most 4,096 of them")
    if not isinstance(manifest_id, str) or not _MANIFEST_ID.fullmatch(manifest_id):
        raise ValueError("seal: manifest_id is 64 lowercase hex characters")
    if type(key_version) is not int or key_version < 1:
        raise ValueError("seal: key_version is a positive integer")
    hrp, public = bech32_decode(recipient)
    if hrp != RECIPIENT_HRP or len(public) != 32:
        raise ValueError("seal: not an age X25519 recipient")
    name, implementation = _implementation()
    if name == "pyrage":
        to = [implementation.x25519.Recipient.from_str(recipient)]
        age_file = bytes(implementation.encrypt(bytes(plaintext), to))
    else:
        age_file = subprocess.run([implementation, "--encrypt", "--recipient", recipient], input=bytes(plaintext),
                                  capture_output=True, check=True).stdout
    if not age_file.startswith(AGE_INTRO):
        raise RuntimeError(f"seal: {name} did not return a binary age v1 file")
    note = f"{NOTE_SCHEMA} {manifest_id} {key_version}\n{armor(age_file)}"
    if len(note) > NOTE_MAX_BYTES:
        raise ValueError("seal: the sealed note would be over 8,192 bytes")
    return note
