"""Explicit local-demo signer. Production supplies its own service signer."""
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def ephemeral_signer():
    """Generate in RAM; no key serialization, file or environment storage."""
    class Signer:
        def __init__(self):
            self._key = Ed25519PrivateKey.generate()
            self.public_key = self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            self.key_id = "local-" + hashlib.sha256(self.public_key).hexdigest()[:16]

        def sign(self, payload):
            return self._key.sign(payload)
    return Signer()
