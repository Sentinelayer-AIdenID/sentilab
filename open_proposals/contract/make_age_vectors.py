"""Builds contracts/open-proposal-v1/vectors-age.json: real age v1 X25519 sealed-note vectors (DESIGN.md section 3.7;
test plan T15).

    python -m open_proposals.contract.make_age_vectors       # needs pyrage or the age binary

Run by hand. age encryption is randomised, so a re-run rewrites every ciphertext; there is no --check, and CI checks
the committed file instead (test_age.py, with no age implementation installed). manifest_id is a placeholder: the
integrator re-seals the same cases per manifest with seal_cases(manifest_id) or build(manifest_id).

The two test identities derive from public phrases at run time (age_tools.identity_from_phrase); the file stores the
phrases and recipients, never a key. Before anything is written, every case is opened with age_tools.reference_decrypt
and, when pyrage imports, with pyrage too; any disagreement aborts the run and writes nothing.
"""
from __future__ import annotations

import base64
import json
import sys
from importlib import metadata
from pathlib import Path

from . import age_tools as at

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "contracts" / "open-proposal-v1" / "vectors-age.json"
PLACEHOLDER_MANIFEST_ID = "f" * 64
KEY_PHRASES = {1: "sentilab-open-proposal-v1 test age key 1, not a secret",
               2: "sentilab-open-proposal-v1 test age key 2, not a secret"}
KIND = "sentilab-open-proposal-v1 age vector"


def compact(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def padded_json(size: int) -> bytes:
    """A JSON object of exactly `size` bytes."""
    value = {"kind": KIND, "pad": "", "text": "a JSON object of exactly 4,096 bytes, the plaintext cap"}
    value["pad"] = "." * (size - len(compact(value)))
    data = compact(value)
    if len(data) != size:
        raise ValueError(f"no JSON object of {size} bytes in this form")
    return data


JSON_PLAINTEXT = compact({"kind": KIND, "text": "a placeholder JSON object, not a proposal"})
TEXT_PLAINTEXT = ("plain text, not JSON: " + KIND).encode("utf-8")
MAX_PLAINTEXT = padded_json(at.PLAINTEXT_MAX_BYTES)

# (id, the key version the first line names, the key version it is sealed to, plaintext, expected, description)
CASES = (
    ("json-key-1", 1, 1, JSON_PLAINTEXT, "opens",
     "A JSON object sealed to key 1, the key version its first line names: it opens."),
    ("json-key-2", 2, 2, JSON_PLAINTEXT, "opens",
     "The same JSON object sealed to key 2, the key version its first line names: it opens."),
    ("names-key-1-sealed-to-key-2", 1, 2, JSON_PLAINTEXT, "unopenable",
     "The same JSON object sealed to key 2 while its first line names key 1: it does not open with key 1, so the "
     "intake rejects it as unsealable. It does open with key 2, so the key version is its only fault."),
    ("not-json-key-1", 1, 1, TEXT_PLAINTEXT, "opens",
     "Plain text, not JSON, sealed to key 1: it opens, and the intake then rejects it as unsealable."),
    ("max-plaintext-key-1", 1, 1, MAX_PLAINTEXT, "opens",
     "A JSON object of exactly 4,096 bytes, the plaintext cap, sealed to key 1: it opens."),
)


def keys() -> list[dict]:
    return [{"key_version": version, "phrase": phrase, "recipient": at.identity_from_phrase(phrase)[1]}
            for version, phrase in KEY_PHRASES.items()]


def seal_cases(manifest_id: str) -> list[dict]:
    """Every case, freshly sealed for `manifest_id`: the reusable part, for re-sealing per manifest."""
    recipients = {key["key_version"]: key["recipient"] for key in keys()}
    cases = []
    for case_id, named, sealed_to, plaintext, expected, description in CASES:
        note = at.seal(plaintext, manifest_id, named, recipients[sealed_to])
        cases.append({"id": case_id, "description": description, "header_key_version": named,
                      "sealed_to_key_version": sealed_to, "expected": expected, "plaintext_bytes": len(plaintext),
                      "plaintext_b64": base64.b64encode(plaintext).decode("ascii"),
                      "note_bytes": len(note.encode("ascii")), "note": note})
    return cases


def build(manifest_id: str = PLACEHOLDER_MANIFEST_ID) -> dict:
    return {
        "description": "Real age v1 X25519 sealed-note vectors for sentilab-open-sealed/1 (DESIGN.md section 3.7; test "
                       "plan T15), sealed by the implementation named under generator. manifest_id is a placeholder: "
                       "re-seal per manifest with make_age_vectors.seal_cases(manifest_id). Open a note with "
                       "age_tools.parse_note, then age_tools.reference_decrypt with the key version its first line "
                       "names.",
        "format": {"first_line": "sentilab-open-sealed/1 <manifest_id> <key_version>",
                   "manifest_id": "64 lowercase hex characters",
                   "key_version": "a positive integer without leading zeros",
                   "armour": "after the first line's LF: -----BEGIN AGE ENCRYPTED FILE-----, canonical padded "
                             "standard base64 in 64-column lines (the last 4 to 64 columns), then "
                             "-----END AGE ENCRYPTED FILE-----; LF line endings; the final LF is optional",
                   "age": "age-encryption.org/v1 to one X25519 recipient; openers ignore unrecognised stanzas",
                   "plaintext_max_bytes": at.PLAINTEXT_MAX_BYTES,
                   "sealed_note_max_bytes": at.NOTE_MAX_BYTES},
        "identity_rule": "Test identities only: the X25519 scalar is sha256 of the UTF-8 phrase, and the recipient is "
                         "Bech32 (human-readable part age) of X25519(scalar, basepoint). Derive the scalar at run "
                         "time; no key is stored here.",
        "generator": {"command": "python -m open_proposals.contract.make_age_vectors", **at.sealer()},
        "manifest_id": manifest_id,
        "keys": keys(),
        "cases": seal_cases(manifest_id),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError("vectors not written: " + message)


def _refuses(opener, age_file: bytes, version: int, failure) -> bool:
    try:
        opener(age_file, version)
    except failure:
        return True
    return False


def verify(document: dict) -> list[str]:
    """Opens every case before anything is written and returns the openers that agreed: the reference opener always,
    pyrage when it imports. Each case must open with the key it was sealed to, and with no other key."""
    scalars = {version: at.identity_from_phrase(phrase)[0] for version, phrase in KEY_PHRASES.items()}
    _require(document["keys"] == keys(), "the keys are not the phrases' identities")

    def reference(age_file, version):
        return at.reference_decrypt(age_file, scalars[version])

    openers = {"age_tools.reference_decrypt": (reference, ValueError)}
    try:
        import pyrage
    except ImportError:
        pyrage = None
    if pyrage is not None:
        identities = {version: pyrage.x25519.Identity.from_str(at.secret_key_string(scalar))
                      for version, scalar in scalars.items()}
        for key in document["keys"]:
            _require(str(identities[key["key_version"]].to_public()) == key["recipient"],
                     f"pyrage derives another recipient for key {key['key_version']}")

        def rage(age_file, version):
            return pyrage.decrypt(age_file, [identities[version]])

        openers[f"pyrage {metadata.version('pyrage')}"] = (rage, pyrage.DecryptError)
    for case in document["cases"]:
        manifest_id, named, age_file = at.parse_note(case["note"])
        plaintext, sealed_to = base64.b64decode(case["plaintext_b64"]), case["sealed_to_key_version"]
        _require(manifest_id == document["manifest_id"] and named == case["header_key_version"],
                 f"{case['id']}: first line")
        _require(len(plaintext) <= at.PLAINTEXT_MAX_BYTES and case["note_bytes"] <= at.NOTE_MAX_BYTES,
                 f"{case['id']}: size caps")
        _require((case["expected"] == "opens") == (named == sealed_to), f"{case['id']}: expected outcome")
        for name, (opener, failure) in openers.items():
            _require(opener(age_file, sealed_to) == plaintext, f"{case['id']}: {name} does not open it")
            for version in KEY_PHRASES:
                if version != sealed_to:
                    _require(_refuses(opener, age_file, version, failure),
                             f"{case['id']}: {name} opens it with key {version}")
    return list(openers)


def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def main(argv) -> int:
    if argv:
        print("usage: python -m open_proposals.contract.make_age_vectors", file=sys.stderr)
        return 2
    document = build()
    generator = document["generator"]
    generator["opened_before_writing_by"] = verify(document)
    OUT.write_bytes(dump(document))
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}: {len(document['cases'])} cases sealed with "
          f"{generator['implementation']} {generator['version']}, opened by "
          f"{', '.join(generator['opened_before_writing_by'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
