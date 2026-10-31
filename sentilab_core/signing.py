"""Adapters for the shared service identity and explicit local demos."""
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def service_signer():
    """Use the flight-record service identity; missing configuration fails closed."""
    from sundai_controller import trust
    from sundai_controller.controller import public_hex

    class Signer:
        def __init__(self):
            self._key = trust.load_service_key()
            public_key_hex = public_hex(self._key)
            self.public_key = bytes.fromhex(public_key_hex)
            self.key_id = trust.key_id_for(public_key_hex)

        def sign(self, payload):
            return self._key.sign(payload)
    return Signer()


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
