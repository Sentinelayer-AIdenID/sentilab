"""Integration with the real shared service loader using runtime-only seeds."""
import base64
import hashlib
import os
import unittest
from unittest import mock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sentilab_core import signing


class ServiceSignerTests(unittest.TestCase):
    def test_service_identity_signs_verifiable_bytes(self):
        # Runtime-only seed and identity: neither is saved in fixtures or on disk.
        seed = os.urandom(32)
        identity = Ed25519PrivateKey.from_private_bytes(seed)
        public_bytes = identity.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        with mock.patch.dict(os.environ, {"FLIGHT_SIGNING_SEED_B64": base64.b64encode(seed).decode()}):
            signer = signing.service_signer()
            reopened = signing.service_signer()
        self.assertEqual(signer.public_key, public_bytes)
        self.assertEqual(signer.key_id, "sha256:" + hashlib.sha256(public_bytes).hexdigest())
        payload = b"view-envelope hash bytes"
        signature = signer.sign(payload)
        self.assertEqual(reopened.sign(payload), signature)
        identity.public_key().verify(signature, payload)
        with self.assertRaises(InvalidSignature):
            identity.public_key().verify(signature, payload + b"changed")

    def test_service_loader_failure_does_not_generate_an_identity(self):
        for value in (None, "", "invalid base64", base64.b64encode(os.urandom(31)).decode()):
            with self.subTest(configured=value is not None), mock.patch.dict(os.environ):
                os.environ.pop("FLIGHT_SIGNING_SEED_B64", None)
                if value is not None:
                    os.environ["FLIGHT_SIGNING_SEED_B64"] = value
                with self.assertRaisesRegex(ValueError, "32-byte Ed25519 seed"):
                    signing.service_signer()


if __name__ == "__main__":
    unittest.main()
