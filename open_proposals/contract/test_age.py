"""Tests for the sealed-note age tooling (age_tools.py) and contracts/open-proposal-v1/vectors-age.json (DESIGN.md
section 3.7; test plan T15).

    python -m unittest -q open_proposals.contract.test_age

Standard library and `cryptography` only, so CI runs them with no age implementation installed: the reference opener
opens ciphertext that an independent implementation sealed (named in the vectors' "generator" entry). The one test
that needs pyrage is skipped when pyrage does not import, as in CI, and is named local-only evidence. Test identities
derive from the vectors' public phrases at run time. No assertion prints a key: checks on secret values use assertTrue
with a fixed message.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import unittest

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from . import age_tools as at
from . import make_age_vectors as generator

try:
    import pyrage
except ImportError:         # CI never installs pyrage
    pyrage = None

VECTORS = json.loads(generator.OUT.read_bytes())
PHRASES = {key["key_version"]: key["phrase"] for key in VECTORS["keys"]}
RECIPIENTS = {key["key_version"]: key["recipient"] for key in VECTORS["keys"]}
CASES = VECTORS["cases"]
NOT_OPENED = "no X25519 stanza opens"
BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
# BIP-173's test vectors, less its over-length invalid string: age drops Bech32's length limit.
BIP173_VALID = ["A12UEL5L", "a12uel5l",
                "an83characterlonghumanreadablepartthatcontainsthenumber1andtheexcludedcharactersbio1tt5tgs",
                "abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw", "11" + "q" * 82 + "c8247j",
                "split1checkupstagehandshakeupstreamerranterredcaperred2y9e3w", "?1ezyfcl"]
BIP173_INVALID = [chr(0x20) + "1nwldj5", chr(0x7F) + "1axkwrx", chr(0x80) + "1eym55h", "pzry9x0s0muk",
                  "1pzry9x0s0muk", "x1b4n0q5v", "li1dgmt3", "de1lg7wt" + chr(0xFF), "A1G7SGD8", "10a06t8", "1qzzfhee"]


def scalar(version: int) -> bytes:
    return at.identity_from_phrase(PHRASES[version])[0]


def plaintext(case) -> bytes:
    return base64.b64decode(case["plaintext_b64"], validate=True)


def age_file(case) -> bytes:
    return at.parse_note(case["note"])[2]


def sample(size: int, seed: int = 0) -> bytes:
    return bytes((31 * index + seed) % 256 for index in range(size))


def is_json_object(data: bytes) -> bool:
    try:
        return isinstance(json.loads(data), dict)
    except ValueError:
        return False


def rewrap(text: str, width: int) -> str:
    """An armour with the same base64 in lines of another width."""
    lines = text.split("\n")
    body = "".join(lines[1:-2])
    return "\n".join([lines[0], *(body[start:start + width] for start in range(0, len(body), width)), lines[-2]]) + "\n"


def header_lines(data: bytes) -> tuple[list[bytes], bytes]:
    """(the header's lines through "--- <mac>", without their LFs; the payload)."""
    end = data.index(b"\n", data.index(b"\n--- ") + 1) + 1
    return data[:end].split(b"\n")[:-1], data[end:]


def join(lines: list[bytes], payload: bytes) -> bytes:
    return b"\n".join(lines) + b"\n" + payload


class Keys(unittest.TestCase):
    def test_the_recipients_derive_from_the_stored_phrases(self):
        self.assertEqual(generator.KEY_PHRASES, PHRASES)
        for version, phrase in PHRASES.items():
            secret, recipient = at.identity_from_phrase(phrase)
            self.assertEqual(RECIPIENTS[version], recipient)
            self.assertEqual(recipient, at.recipient_from_scalar(secret))
            hrp, public = at.bech32_decode(recipient)
            self.assertEqual(("age", 32), (hrp, len(public)))
        self.assertEqual(len(PHRASES), len(set(RECIPIENTS.values())))

    def test_the_secret_key_string_round_trips_and_is_never_shown(self):
        for version in PHRASES:
            secret = scalar(version)
            text = at.secret_key_string(secret)
            self.assertTrue(text == text.upper() and at.bech32_decode(text) == (at.SECRET_HRP, secret),
                            "the secret-key string does not round-trip (value withheld)")
        with self.assertRaises(ValueError):
            at.secret_key_string(bytes(31))


class Bech32(unittest.TestCase):
    def test_round_trips(self):
        for hrp in ("age", "a", at.SECRET_HRP, "?"):
            for size in (0, 1, 2, 5, 31, 32, 33, 64, 100):
                data = sample(size, len(hrp))
                text = at.bech32_encode(hrp, data)
                self.assertEqual((hrp, data), at.bech32_decode(text))
                self.assertEqual((hrp, data), at.bech32_decode(text.upper()))

    def test_bip173_valid_strings(self):
        for text in BIP173_VALID:
            with self.subTest(text=text):
                hrp, data = at.bech32_decode(text)
                self.assertEqual(text.lower(), at.bech32_encode(hrp, data))

    def test_bip173_invalid_strings_and_every_single_substitution(self):
        recipient = RECIPIENTS[1]
        substituted = [recipient[:index] + ("p" if recipient[index] == "q" else "q") + recipient[index + 1:]
                       for index in range(len("age1"), len(recipient))]
        mixed = recipient[:20] + recipient[20:].upper()
        for text in BIP173_INVALID + substituted + [mixed]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                at.bech32_decode(text)

    def test_non_zero_padding_bits_are_refused(self):
        values = at._convert_bits(bytes(32), 8, 5, True)    # 52 groups; the last carries 4 padding bits
        values[-1] |= 1
        polymod = at._polymod(at._hrp_expand("age") + values + [0] * 6) ^ 1
        checksum = [(polymod >> (5 * (5 - index))) & 31 for index in range(6)]
        with self.assertRaisesRegex(ValueError, "padding bits"):
            at.bech32_decode("age1" + "".join(at.BECH32_CHARSET[value] for value in values + checksum))

    def test_encoding_takes_a_lowercase_human_readable_part(self):
        for hrp in ("", "AGE", "Age", "a b", "a" + chr(0x7F)):
            with self.subTest(hrp=hrp), self.assertRaises(ValueError):
                at.bech32_encode(hrp, b"x")


class Armour(unittest.TestCase):
    def test_round_trip_and_the_canonical_layout(self):
        for size in [*range(1, 200), 4500, 6000]:
            data = sample(size)
            text = at.armor(data)
            self.assertEqual(data, at.dearmor(text))
            self.assertEqual(data, at.dearmor(text[:-1]))                  # the final LF is optional
            self.assertEqual(data, at.dearmor(text.encode("ascii")))
            lines = text.split("\n")
            self.assertEqual([at.ARMOR_BEGIN, at.ARMOR_END, ""], [lines[0], lines[-2], lines[-1]])
            body, encoded = lines[1:-2], base64.b64encode(data).decode("ascii")
            self.assertEqual(encoded, "".join(body))
            self.assertEqual({64}, {len(line) for line in body[:-1]} or {64})
            self.assertEqual(len(encoded) % 64 or 64, len(body[-1]))      # a full last line when 64 divides the length
        with self.assertRaises(ValueError):
            at.armor(b"")

    def test_every_other_form_is_refused(self):
        text = at.armor(sample(100))        # 136 base64 characters: lines of 64, 64 and 8, the last ending "=="
        lines = text.split("\n")
        body, last = lines[1:-2], lines[-3]
        joined = "".join(body)
        self.assertTrue(len(body) == 3 and last.endswith("==") and ("+" in joined or "/" in joined))
        value = BASE64.index(last[-3])      # its 4 low bits are padding, so zero
        self.assertEqual(0, value & 15)
        tail = "\n" + at.ARMOR_END + "\n"
        refused = {
            "BEGIN in lower case": text.replace(at.ARMOR_BEGIN, at.ARMOR_BEGIN.lower()),
            "BEGIN with a doubled space": text.replace("BEGIN AGE", "BEGIN  AGE"),
            "BEGIN short of a dash": text.replace(at.ARMOR_BEGIN, at.ARMOR_BEGIN[1:]),
            "another label": text.replace("AGE ENCRYPTED FILE", "PGP MESSAGE"),
            "END altered": text.replace(at.ARMOR_END, at.ARMOR_END.replace("END", "End")),
            "END missing": text[:text.index(at.ARMOR_END)],
            "lines of 76": rewrap(text, 76),
            "lines of 63": rewrap(text, 63),
            "one line": rewrap(text, len(joined)),
            "a short line before the last": "\n".join([lines[0], joined[:60], joined[60:124], joined[124:]]) + tail,
            "an empty line in the body": "\n".join([lines[0], body[0], "", *body[1:]]) + tail,
            "an empty line before END": text.replace(tail, "\n" + tail),
            "CRLF line endings": text.replace("\n", chr(13) + "\n"),
            "a CR before the final LF": text[:-1] + chr(13) + "\n",
            "a blank line before BEGIN": "\n" + text,
            "a space before BEGIN": " " + text,
            "a space after END": text[:-1] + " \n",
            "a space after the final LF": text + " ",
            "two final LFs": text + "\n",
            "text after END": text + "more",
            "two armour blocks": text + text,
            "padding removed": text.replace("==" + tail, tail),
            "padding doubled": text.replace("==" + tail, "====" + tail),
            "non-zero padding bits": text.replace(last + tail, last[:-3] + BASE64[value + 1] + "==" + tail),
            "the URL-safe alphabet": text.replace("+", "-").replace("/", "_"),
            "a space in a line": text.replace(body[0], body[0][:10] + " " + body[0][11:]),
            "a tab in a line": text.replace(body[0], body[0][:10] + chr(9) + body[0][11:]),
            "a non-ASCII character": text.replace(body[0], body[0][:10] + chr(0xE9) + body[0][11:]),
            "an empty body": at.ARMOR_BEGIN + tail,
            "BEGIN alone": at.ARMOR_BEGIN + "\n",
            "nothing": "",
        }
        for name, bad in refused.items():
            self.assertNotEqual(text, bad, name)                            # every mutation landed
            with self.subTest(name), self.assertRaises(ValueError):
                at.dearmor(bad)


class SealedNotes(unittest.TestCase):
    def test_the_cases_are_the_generators(self):
        expected = [(case_id, named, sealed_to, base64.b64encode(plain).decode("ascii"), outcome, description)
                    for case_id, named, sealed_to, plain, outcome, description in generator.CASES]
        stored = [(case["id"], case["header_key_version"], case["sealed_to_key_version"], case["plaintext_b64"],
                   case["expected"], case["description"]) for case in CASES]
        self.assertEqual(expected, stored)
        self.assertEqual({"opens", "unopenable"}, {case["expected"] for case in CASES})

    def test_every_note_is_well_formed_and_within_the_caps(self):
        manifest_id = VECTORS["manifest_id"]
        self.assertIsNotNone(re.fullmatch("[0-9a-f]{64}", manifest_id))
        for case in CASES:
            with self.subTest(case["id"]):
                note, plain = case["note"], plaintext(case)
                first, _, armour = note.partition("\n")
                self.assertEqual(f"{at.NOTE_SCHEMA} {manifest_id} {case['header_key_version']}", first)
                self.assertEqual((manifest_id, case["header_key_version"]), at.parse_note(note)[:2])
                self.assertEqual(armour, at.armor(at.dearmor(armour)))     # canonical, LF only, with its final LF
                self.assertTrue(age_file(case).startswith(at.AGE_INTRO))
                self.assertEqual(len(plain), case["plaintext_bytes"])
                self.assertLessEqual(len(plain), at.PLAINTEXT_MAX_BYTES)
                self.assertEqual(len(note.encode("ascii")), case["note_bytes"])
                self.assertLessEqual(case["note_bytes"], at.NOTE_MAX_BYTES)
        self.assertEqual(at.PLAINTEXT_MAX_BYTES, max(len(plaintext(case)) for case in CASES))

    def test_each_opens_case_opens_with_the_key_version_its_first_line_names(self):
        opened = 0
        for case in CASES:
            if case["expected"] == "opens":
                with self.subTest(case["id"]):
                    _, named, data = at.parse_note(case["note"])
                    self.assertEqual(plaintext(case), at.reference_decrypt(data, scalar(named)))
                    # as a shell's "$(cat sealed.txt)" posts it, without the final LF
                    self.assertEqual(plaintext(case), at.reference_decrypt(at.parse_note(case["note"][:-1])[2],
                                                                           scalar(named)))
                    opened += 1
        self.assertEqual(sum(case["expected"] == "opens" for case in CASES), opened)

    def test_the_unopenable_case_fails_with_its_named_key_and_only_because_of_it(self):
        unopenable = [case for case in CASES if case["expected"] == "unopenable"]
        self.assertTrue(unopenable)
        for case in unopenable:
            _, named, data = at.parse_note(case["note"])
            self.assertNotEqual(named, case["sealed_to_key_version"])
            with self.assertRaisesRegex(ValueError, NOT_OPENED):
                at.reference_decrypt(data, scalar(named))
            self.assertEqual(plaintext(case), at.reference_decrypt(data, scalar(case["sealed_to_key_version"])))

    def test_no_note_opens_with_another_key(self):
        stranger = at.identity_from_phrase("sentilab-open-proposal-v1 test age key 3, never sealed to")[0]
        for case in CASES:
            data = age_file(case)
            others = [scalar(version) for version in PHRASES if version != case["sealed_to_key_version"]]
            for other in others + [stranger]:
                with self.subTest(case["id"]), self.assertRaisesRegex(ValueError, NOT_OPENED):
                    at.reference_decrypt(data, other)

    def test_the_plaintexts(self):
        by_id = {case["id"]: plaintext(case) for case in CASES}
        self.assertEqual(["not-json-key-1"], [case_id for case_id, plain in by_id.items() if not is_json_object(plain)])
        self.assertEqual(at.PLAINTEXT_MAX_BYTES, len(by_id["max-plaintext-key-1"]))
        self.assertEqual(by_id["json-key-1"], by_id["json-key-2"])
        self.assertEqual(by_id["json-key-1"], by_id["names-key-1-sealed-to-key-2"])

    def test_unrecognised_stanzas_are_ignored(self):
        """rage adds a random "<x>-grease" stanza to every file it seals, so opening the vectors shows that the
        reference opener ignores the stanzas it does not recognise, as age.md requires."""
        types = set()
        for case in CASES:
            lines, _ = header_lines(age_file(case))
            types |= {line.split(b" ")[1] for line in lines if line.startswith(b"-> ")}
        self.assertIn(b"X25519", types)
        self.assertTrue(types - {b"X25519"}, "no vector carries an unrecognised stanza")

    def test_parse_note_is_strict(self):
        case = CASES[0]
        note, manifest_id, version = case["note"], VECTORS["manifest_id"], case["header_key_version"]
        first, _, armour = note.partition("\n")
        self.assertEqual((manifest_id, version, age_file(case)), at.parse_note(note.encode("ascii")))
        self.assertEqual((manifest_id, version, age_file(case)), at.parse_note(note[:-1]))
        schema = at.NOTE_SCHEMA
        bad_first_lines = [
            f"sentilab-open-sealed/2 {manifest_id} {version}",
            f"{schema} {manifest_id.upper()} {version}",
            f"{schema} {manifest_id[:-1]} {version}",
            f"{schema} {manifest_id}f {version}",
            f"{schema} {manifest_id} 0",
            f"{schema} {manifest_id} 0{version}",
            f"{schema} {manifest_id} -{version}",
            f"{schema} {manifest_id} +{version}",
            f"{schema} {manifest_id} {version}.0",
            f"{schema} {manifest_id}",
            f"{schema}  {manifest_id} {version}",
            f"{schema} {manifest_id} {version} ",
            f" {schema} {manifest_id} {version}",
            f"{schema} {manifest_id} {version}" + chr(13),
            f"{first}\n",
        ]
        for line in bad_first_lines:
            self.assertNotEqual(first, line)
            with self.subTest(line=line), self.assertRaises(ValueError):
                at.parse_note(line + "\n" + armour)
        for bad in (armour, first + "\n", first, "", '{"schema": "sentilab-open-proposal/1"}'):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                at.parse_note(bad)
        oversize = first + "\n" + at.armor(bytes(7000))
        self.assertGreater(len(oversize), at.NOTE_MAX_BYTES)
        with self.assertRaisesRegex(ValueError, "8,192"):
            at.parse_note(oversize)

    def test_seal_refuses_bad_arguments_before_sealing(self):
        recipient, manifest_id = RECIPIENTS[1], VECTORS["manifest_id"]
        for plain, mid, version, to in ((bytes(at.PLAINTEXT_MAX_BYTES + 1), manifest_id, 1, recipient),
                                        ("text", manifest_id, 1, recipient),
                                        (b"x", manifest_id.upper(), 1, recipient),
                                        (b"x", manifest_id[:-1], 1, recipient),
                                        (b"x", manifest_id, 0, recipient),
                                        (b"x", manifest_id, True, recipient),
                                        (b"x", manifest_id, 1, recipient[:-1] + "q"),
                                        (b"x", manifest_id, 1, at.bech32_encode("age", bytes(31)))):
            with self.subTest(version=version, recipient=to[:12]), self.assertRaises(ValueError):
                at.seal(plain, mid, version, to)


class Tampering(unittest.TestCase):
    """Each check in the reference opener can fail, and fails for the reason it names."""

    def setUp(self):
        case = CASES[0]
        self.plain, self.key, self.data = plaintext(case), scalar(case["sealed_to_key_version"]), age_file(case)
        self.lines, self.payload = header_lines(self.data)
        self.x25519 = next(index for index, line in enumerate(self.lines) if line.startswith(b"-> X25519 "))
        self.assertEqual(self.plain, at.reference_decrypt(self.data, self.key))        # the untouched file opens

    def refused(self, data: bytes, reason: str) -> None:
        self.assertNotEqual(self.data, data)
        with self.assertRaisesRegex(ValueError, reason):
            at.reference_decrypt(data, self.key)

    def test_the_header(self):
        lines, payload, x = self.lines, self.payload, self.x25519
        mac = base64.b64decode(lines[-1][4:] + b"=")
        flipped = base64.b64encode(bytes((mac[0] ^ 1,)) + mac[1:]).rstrip(b"=")
        self.refused(join(lines[:-1] + [b"--- " + flipped], payload), "bad header MAC")
        # A well-formed stanza nobody recognises: only the MAC, which covers the whole header, can catch it.
        self.refused(join(lines[:-1] + [b"-> sentilab-test-stanza", b""] + lines[-1:], payload), "bad header MAC")
        self.refused(join([b"age-encryption.org/v2"] + lines[1:], payload), "not an age-encryption.org/v1 file")
        self.refused(self.data.replace(b"\n", b"\r\n", 1), "not an age-encryption.org/v1 file")
        self.refused(join(lines[:x] + [lines[x] + b" extra"] + lines[x + 1:], payload), "exactly one argument")
        self.refused(join(lines[:x] + [lines[x] + b"="] + lines[x + 1:], payload), "canonical unpadded base64")
        zero_share = b"-> X25519 " + base64.b64encode(bytes(32)).rstrip(b"=")
        self.refused(join(lines[:x] + [zero_share] + lines[x + 1:], payload), "low-order")
        self.refused(join(lines[:x + 1] + lines[x + 2:], payload), "canonical unpadded base64|over 64 columns")
        self.refused(join(lines[:x] + [lines[x].replace(b"-> ", b"->")] + lines[x + 1:], payload),
                     "unexpected header line")
        self.refused(join(lines[:x] + [lines[x].replace(b"X25519 ", b"X25519  ")] + lines[x + 1:], payload),
                     "malformed stanza arguments")
        self.refused(join(lines[:-1] + [lines[-1][:-1]], payload), "canonical unpadded base64|not 32 bytes")
        # 32 bytes in 43 characters leave 2 padding bits in the last one. The MAC line is not under the MAC, so only
        # the canonical-encoding rule stops a second spelling of the same MAC.
        value = BASE64.index(chr(lines[-1][-1]))
        self.assertEqual(0, value & 3)
        respelled = lines[-1][:-1] + BASE64[value + 1].encode("ascii")
        self.refused(join(lines[:-1] + [respelled], payload), "canonical unpadded base64")
        self.refused(self.data[:len(join(lines, b"")) - 1], "truncated header")

    def test_the_payload(self):
        data, start = self.data, len(self.data) - len(self.payload)       # start: the payload's 16-byte nonce

        def flip(position: int) -> bytes:
            return data[:position] + bytes((data[position] ^ 1,)) + data[position + 1:]

        for position in (start, start + 16, len(data) - 1):              # the nonce, the ciphertext, the tag
            self.refused(flip(position), "payload chunk failed authentication")
        self.refused(data[:-1], "payload chunk failed authentication")
        self.refused(data + bytes(1), "payload chunk failed authentication")
        for cut in (start + 16, start + 15, start):                       # no chunk, a cut nonce, no payload
            self.refused(data[:cut], "truncated payload")

    def test_the_stream_rules(self):
        """age.md, Payload: the final chunk is flagged, may be full, and is empty only when the whole payload is. The
        vectors fit in one chunk, so the chunks here are sealed directly with ChaCha20-Poly1305 under a phrase key."""
        key = hashlib.sha256(b"sentilab-open-proposal-v1 test payload key, not a secret").digest()
        aead = ChaCha20Poly1305(key)

        def chunk(counter: int, final: bool, plain: bytes) -> bytes:
            return aead.encrypt(counter.to_bytes(11, "big") + bytes((1 if final else 0,)), plain, None)

        full = sample(64 * 1024, 9)
        self.assertEqual(full, at._open_stream(key, chunk(0, True, full)))
        self.assertEqual(full + b"x", at._open_stream(key, chunk(0, False, full) + chunk(1, True, b"x")))
        self.assertEqual(b"", at._open_stream(key, chunk(0, True, b"")))
        for name, bad in (("no final chunk", chunk(0, False, full)),
                          ("a short chunk not flagged final", chunk(0, False, b"x")),
                          ("data after the final chunk", chunk(0, True, b"x") + chunk(1, True, b"y")),
                          ("an empty final chunk after a full one", chunk(0, False, full) + chunk(1, True, b"")),
                          ("a full chunk flagged final, then more", chunk(0, True, full) + chunk(1, True, b"x"))):
            with self.subTest(name), self.assertRaises(ValueError):
                at._open_stream(key, bad)


@unittest.skipUnless(pyrage is not None, "local-only evidence: pyrage does not import here (CI never installs it)")
class LocalOnlyPyrageEvidence(unittest.TestCase):
    """Local-only evidence, never run in CI: an independent age implementation (pyrage, on the rage library) agrees
    with the derived recipients, the reference opener and the armour."""

    def test_local_only_evidence_pyrage_agrees_with_the_reference(self):
        identities = {version: pyrage.x25519.Identity.from_str(at.secret_key_string(scalar(version)))
                      for version in PHRASES}
        recipients = {version: pyrage.x25519.Recipient.from_str(RECIPIENTS[version]) for version in PHRASES}
        for version, identity in identities.items():
            self.assertEqual(RECIPIENTS[version], str(identity.to_public()))
        for case in CASES:      # rage opens each note, binary or armoured, with the key it was sealed to and no other
            data, armour, sealed_to = age_file(case), case["note"].partition("\n")[2], case["sealed_to_key_version"]
            self.assertEqual(plaintext(case), pyrage.decrypt(data, [identities[sealed_to]]))
            self.assertEqual(plaintext(case), pyrage.decrypt(armour.encode("ascii"), [identities[sealed_to]]))
            for version in PHRASES:
                if version != sealed_to:
                    with self.assertRaises(pyrage.DecryptError):
                        pyrage.decrypt(data, [identities[version]])
        for size in (0, 1, 4096, 65535, 65536, 65537, 2 * 65536 + 3):     # around the 64 KiB STREAM chunks
            data = sample(size, 5)
            for version in PHRASES:
                self.assertEqual(data, at.reference_decrypt(pyrage.encrypt(data, [recipients[version]]),
                                                            scalar(version)))
        full_last_lines = 0
        for attempt in range(2000):     # rage's own armour, LF-normalised, passes the strict reader
            raw = pyrage.encrypt(b"armour", [recipients[1]], armored=True).decode("ascii")
            text = raw.replace(chr(13) + "\n", "\n")
            if raw != text:             # rage on Windows ends armour lines in CRLF, which the strict reader refuses
                with self.assertRaises(ValueError):
                    at.dearmor(raw)
            self.assertEqual(b"armour", at.reference_decrypt(at.dearmor(text), scalar(1)))
            full_last_lines += len(text.split("\n")[-3]) == 64
            if full_last_lines and attempt >= 50:
                break
        self.assertGreater(full_last_lines, 0)      # a full 64-column last line included
